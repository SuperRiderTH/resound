#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Description:  Sync all Plex playlists to shared users.
# Author:       SuperRiderTH, /u/SwiftPanda16
# Requires:     plexapi, requests, xmltodict

import sys
import requests
import xmltodict
import plexapi

from plexapi.server import PlexServer
from plexapi.exceptions import BadRequest, NotFound, Unauthorized
from packaging import version


# Recent versions of Plex return a status code when deleting a playlist
# that the PlexAPI doesn't understand until a version after 4.1.2.
# We want to catch that and check it if our version is at or lower than that.
PLEXAPI_CHECK_204 = version.parse(plexapi.VERSION) <= version.parse("4.1.2")


# Note: I am disabling warnings for urllib3 because we are making an unverified
# HTTPS request. This is just to hide the unverified HTTPS request warning, as
# this should be running on the server itself, accessing localhost.
# HTTPS use cases are not supported at this time, but may work.
import urllib3
urllib3.disable_warnings()


### Plex Settings ###

PLEX_URL = 'http://localhost:32400'
PLEX_TOKEN = 'xxxxxxxxxxxxxxxxxxxx'


### User Settings ###

# If the whitelist is empty, all users will be synchronized.
# An alternative name can be added with a comma, for example: "user@email.com,Name"
# Example: USER_WHITELIST  = ['User', 'User2@email.com,User2', 'User3,Real Name of User 3']

USER_WHITELIST  = []


# If you want to include the server owner in syncing, this must be set to True. 
INCLUDE_SERVER_OWNER    = True
SERVER_OWNER_USER       = 'ServerOwner'
# Note: This isn't actually the user.
# It is just used for this script so it can be whatever you want.
# Can also have an alternative name, example: "ServerOwner,Name".


### Sync Settings ###

# These are the characters used in playlists to determine if a playlist
# should be ignored, or was made by this script on a prior run.
IGNORE_CHARACTER        = "!"
SYNC_CHARACTER          = "|"


### Variables that should not be touched by humans ##

MAJOR_VERSION = 2
MINOR_VERSION = 0
PATCH_VERSION = 1

VERSION = f"{MAJOR_VERSION}.{MINOR_VERSION}.{PATCH_VERSION}"

USERS           = []
NAMES           = []
USER_SERVER     = []

PLEX_SERVER     = PlexServer(PLEX_URL, PLEX_TOKEN)
MY_PLEX         = PLEX_SERVER.myPlexAccount()

ARG_CLEAN               = False
ARG_DRYRUN              = False


## CODE BELOW ##

def fetch_plex_api(path='', method='GET', plextv=False, **kwargs):
    """Fetches data from the Plex API"""

    url = 'https://plex.tv' if plextv else PLEX_URL.rstrip('/')

    headers = {'X-Plex-Token': PLEX_TOKEN,
               'Accept': 'application/json'}

    params = {}
    if kwargs:
        params.update(kwargs)

    try:
        if method.upper() == 'GET':
            r = requests.get(url + path,
                             headers=headers, params=params, verify=False)
        elif method.upper() == 'POST':
            r = requests.post(url + path,
                              headers=headers, params=params, verify=False)
        elif method.upper() == 'PUT':
            r = requests.put(url + path,
                             headers=headers, params=params, verify=False)
        elif method.upper() == 'DELETE':
            r = requests.delete(url + path,
                                headers=headers, params=params, verify=False)
        else:
            print("Invalid request method provided: {method}".format(method=method))
            return

        if r and len(r.content):
            if 'application/json' in r.headers['Content-Type']:
                return r.json()
            elif 'application/xml' in r.headers['Content-Type']:
                return xmltodict.parse(r.content)
            else:
                return r.content
        else:
            return r.content

    except Exception as e:
        print("Error fetching from Plex API: {err}".format(err=e))

def get_user_tokens(server_id):
    api_users = fetch_plex_api('/api/users', plextv=True)
    api_shared_servers = fetch_plex_api('/api/servers/{server_id}/shared_servers'.format(server_id=server_id), plextv=True)
    user_ids = {user['@id']: user.get('@username', user.get('@title')) for user in api_users['MediaContainer']['User']}
    users = {user_ids[user['@userID']]: user['@accessToken'] for user in api_shared_servers['MediaContainer']['SharedServer']}
    return users
    
def init_users():

    global SERVER_OWNER_USER, USER_WHITELIST, USER_SERVER

    # Get all the users on the server for verification, or to use if whitelist is empty.
    plex_users = get_user_tokens(PLEX_SERVER.machineIdentifier)

    print ("========================================")
    print ("Users")
    print ("========================================")

    # Use the list of users if there is no whitelist.
    if len(USER_WHITELIST) == 0:
        for x in plex_users:
            USER_WHITELIST.append(x)
    else:
        print ("------------------------------")
        print ("Whitelist exists, syncing users:")
        print ("------------------------------")

    # If we are including the server owner, we want to add them to the whitelist.
    if INCLUDE_SERVER_OWNER:
        USER_WHITELIST.append(SERVER_OWNER_USER)
        
        if len(SERVER_OWNER_USER.split(',')) > 1:
            SERVER_OWNER_USER = SERVER_OWNER_USER.split(',')[0]

    # Go through and cleanup the whitelist for alternative names.
    for x in USER_WHITELIST:
        if len(x.split(',')) > 1:
            USERS.append(x.split(',')[0])
            NAMES.append(x.split(',')[1])
        else:
            USERS.append(x)
            NAMES.append(x)

    # Verify that all the users actually exist in the server.
    for x in USERS:
        if x in plex_users or x == SERVER_OWNER_USER:
            print(x)
        else:
            print ('User "' + x + '" not found! Aborting.')
            return True

    print ("========================================")

    print("Getting user servers...")

    # Login as all the users, store their servers for later.
    for x in USERS:
        if x == SERVER_OWNER_USER:
            USER_SERVER.append(PLEX_SERVER)
        else:
            user = MY_PLEX.user(x)
            token = user.get_token(PLEX_SERVER.machineIdentifier)
            USER_SERVER.append(PlexServer(PLEX_URL, token))

    return False


def get_owner_user(playlistTitle):
    for name in NAMES:
        if name == playlistTitle.split(": ")[0].strip(SYNC_CHARACTER):
            return USERS[NAMES.index(name)]
    assert "User not found!"

def process_playlists():

    for user in USERS:

        print ("========================================")
        print (NAMES[USERS.index(user)] + " - " + user)
        print ("========================================")

        for playlist in USER_SERVER[USERS.index(user)].playlists():
            if playlist.title.startswith(IGNORE_CHARACTER):
                print("Ignoring " + playlist.title)
                continue

            # Get the items in the playlist, to check if it actually has items.
            playlistItems = playlist.items()

            # We also want to ignore smart playlists.
            if playlist.smart :
                print("Playlist " + playlist.title + " is a smart playlist, ignoring...")
            
            # And also ignore empty playlists.
            elif not playlistItems:
                print("Playlist " + playlist.title + " is empty.")

            # If we find a synced playlist, we want to see if it exists.
            else:
                if playlist.title.startswith(SYNC_CHARACTER):

                    if ARG_CLEAN:
                        if not ARG_DRYRUN:
                            print("Removing playlist: " + playlist.title)
                        else:
                            print("Dry run, not removing: " + playlist.title)
                    else:
                        print("Checking if synced playlist exists: " + playlist.title)
                    
                    # We want to see if the playlist exists in the original user.
                    # If it does not, we just remove it.
                    playlistExists = False
                    owner = get_owner_user(playlist.title)

                    # We need to see if the owner of the playlist actually exists,
                    # this will handle any synced playlists from removed users.
                    if owner in USERS:
                        for playlistCheck in USER_SERVER[USERS.index(owner)].playlists():
                            if playlist.title.endswith(playlistCheck.title):
                                playlistExists = True
                                pass
                            pass

                    # If we are cleaning up the playlists, we just pretend they all don't exist.
                    if ARG_CLEAN:
                        playlistExists = False

                    # If the play list exists, we move on and don't 
                    if playlistExists:
                        pass
                    else:
                        # We grab a potential exception to see if it is actually alright.
                        if PLEXAPI_CHECK_204:
                            try:
                                USER_SERVER[USERS.index(user)].playlist(playlist.title).delete()
                            except BadRequest as e:
                                message = getattr(e, 'message', str(e))
                                if message.startswith("(204)"):
                                    pass
                                else:
                                    raise BadRequest(message)
                        else:
                            if not ARG_DRYRUN:
                                USER_SERVER[USERS.index(user)].playlist(playlist.title).delete()
                                if not ARG_CLEAN:
                                    print("Playlist not found, deleted playlist...")
                            else:
                                print("Playlist not found.")
                                
                # We found an actual playlist, so we want to sync it with other users.
                else:
                    if ARG_CLEAN:
                        pass
                    else:
                        print ("========================================")
                        print("Found: " + playlist.title)
                        print ("========================================")

                        for userCheck in USERS:

                            if USERS.index(userCheck) != USERS.index(user):

                                # We need to find the playlist, otherwise we create it.
                                playlistExists = False

                                playlistCheckName = SYNC_CHARACTER + NAMES[USERS.index(user)] + ": " + playlist.title

                                for playlistCheck in USER_SERVER[USERS.index(userCheck)].playlists():
                                    if playlistCheckName == playlistCheck.title:
                                        playlistExists = True
                                        targetPlaylist = playlistCheck
                                        pass
                                    pass
                                pass

                                # If the playlist exists, we check the items and add or remove them as necessary.
                                if playlistExists:
                                    print ("------------------------------")
                                    print("Syncing playlist for: " + NAMES[USERS.index(userCheck)])
                                    print ("------------------------------")
                                    
                                    
                                    # Remove items if not found in original playlist.
                                    for item in targetPlaylist.items():
                                        if item not in playlist.items():
                                            if not ARG_DRYRUN:
                                                print('- "' + item.title + '"' + " not found in playlist! Removing...")
                                                targetPlaylist.removeItems(item)
                                                pass
                                            else:
                                                print('- "' + item.title + '"' + " not found in playlist!")
                                            pass
                                        pass

                                    # Add items if not found in synced playlist.
                                    for item in playlist.items():
                                        if item not in targetPlaylist.items():
                                            if not ARG_DRYRUN:
                                                print('- "' + item.title + '"'  + " not found in playlist! Adding...")
                                                targetPlaylist.addItems(item)
                                                pass
                                            else:
                                                print('- "' + item.title + '"'  + " not found in playlist!")
                                            pass
                                        pass

                                # Playlist does not exist, so we just clone it in it's entirety.
                                else:
                                    
                                    if not ARG_DRYRUN:
                                        print ("Creating '" + playlistCheckName + "' for " + NAMES[USERS.index(userCheck)])
                                        USER_SERVER[USERS.index(userCheck)].createPlaylist( playlistCheckName, items=playlist.items() )
                                        pass
                                    else:
                                        print ("Dry run, not creating '" + playlistCheckName + "' for " + NAMES[USERS.index(userCheck)])
                                    pass
                            pass


def main():

    print ("")

    print ("Resound Version: " + VERSION)
    print ("Plex Server Version: " + PLEX_SERVER.version)
    print ("Python-PlexAPI Version : " + plexapi.VERSION)

    global ARG_CLEAN, ARG_DRYRUN

    # Check for any arguments.
    if len(sys.argv) > 1:
        for x in sys.argv:
            if x == "clean":
                ARG_CLEAN = True
            if x == "dryrun":
                ARG_DRYRUN = True

    if ARG_CLEAN:
        print ("========================================")
        print ("Clean argument detected, just removing playlists.")
        print ("========================================")

    if ARG_DRYRUN:
        print ("========================================")
        print ("Dry run, will not modify playlists.")
        print ("========================================")

    if PLEXAPI_CHECK_204:
        print ("PlexAPI version is <= 4.1.2, will ignore status code 204 when deleting.")
        print ("For details:\nhttps://github.com/pkkid/python-plexapi/pull/580\n")

    if init_users():
        return

    if process_playlists():
        return

    return

if __name__ == "__main__":
    main()
    print ("========================================")
    print("Done.")
