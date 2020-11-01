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
# Can also have an alternative name.


### Sync Settings ###

# These are the characters used in playlists to determine if a playlist
# should be ignored, or was made by this script on a prior run.
IGNORE_CHARACTER        = "!"
SYNC_CHARACTER          = "|"

# Used by the script internally for playlist handling.
# Can be changed, but should not be an issue.
PLAYLIST_DELIMITER      = "-/-"


### Variables that should not be touched by humans ##

USERS           = []
NAMES           = []
USER_SERVER     = []

PLEX_SERVER     = PlexServer(PLEX_URL, PLEX_TOKEN)
MY_PLEX         = PLEX_SERVER.myPlexAccount()

PLAYLISTS_GOOD          = []
PLAYLISTS_GOOD_ITEMS    = []
PLAYLISTS_BAD           = []

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
        print("Whitelist exists, syncing users:")
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
            print (x)
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

def init_playlists():

    for user in USERS:
        userIndex = USERS.index(user)

        print ("========================================")
        print (NAMES[userIndex] + " - " + user)

        # Check the playlists for our special characters.
        for playlist in USER_SERVER[userIndex].playlists():
            if playlist.title.startswith(IGNORE_CHARACTER):
                print("Ignoring " + playlist.title)
                continue
            if playlist.title.startswith(SYNC_CHARACTER):
                print("Playlist '" + playlist.title + "' is a synced playlist, will remove. ")
                PLAYLISTS_BAD.append(user + PLAYLIST_DELIMITER + playlist.title)
                #print(playlist)
                continue

            # Get the items in the playlist, to check if it actually has items.
            playlistItems = playlist.items()

            # We also want to ignore smart playlists.
            if playlist.smart :
                print("Playlist " + playlist.title + " is a smart playlist, ignoring...")
            elif not playlistItems:
                print("Playlist " + playlist.title + " is empty.")
            else:
                print("Copying " + playlist.title)
                PLAYLISTS_GOOD.append(user + PLAYLIST_DELIMITER + playlist.title)
                PLAYLISTS_GOOD_ITEMS.append(playlistItems)
                #for x in playlistItems:
                #    print(x)
                #    print(x.guid)
                #    print(x.title)
                #    print(x.artist().title)
                #    print(x.addedAt)
                #    print(x.viewCount)
            #print(playlist)

    print ("========================================")
    print ("Playlists to remove:")
    print (PLAYLISTS_BAD)

    if ARG_CLEAN == False:
        print ("========================================")
        print ("Playlists to copy:")
        print (PLAYLISTS_GOOD)

    print ("")

    return False

def handle_playlists():

    if len(PLAYLISTS_GOOD) != len(PLAYLISTS_GOOD_ITEMS):
        print("Number of playlists do not match number of items, stopping.")
        return True

    # Remove the bad playlists.
    for x in PLAYLISTS_BAD:
        user = x.split(PLAYLIST_DELIMITER)[0].strip(SYNC_CHARACTER)
        playlist = x.split(PLAYLIST_DELIMITER)[1]
        print("Removing '" + playlist + "' from " + user)

        if not ARG_DRYRUN:

            # We grab a potential exception to see if it is actually alright.
            if PLEXAPI_CHECK_204:
                try:
                    USER_SERVER[USERS.index(user)].playlist(playlist).delete()
                except BadRequest as e:
                    message = getattr(e, 'message', str(e))
                    if message.startswith("(204)"):
                        pass
                    else:
                        raise BadRequest(message)
            else:
                USER_SERVER[USERS.index(user)].playlist(playlist).delete()
            

    if ARG_CLEAN:
        return False

    print ("------------------------------")
    # Recreate the good playlists on each user.
    for playlist in PLAYLISTS_GOOD:
        owner = playlist.split(PLAYLIST_DELIMITER)[0].strip(SYNC_CHARACTER)
        playlist_name = playlist.split(PLAYLIST_DELIMITER)[1]

        for user in USERS:
            if not playlist.startswith(user):
                playlist_display_name = ( SYNC_CHARACTER + NAMES[USERS.index(owner)] + ": " + playlist_name )
                print ("Creating '" + playlist_display_name + "' for " + user)
                if not ARG_DRYRUN:
                    USER_SERVER[USERS.index(user)].createPlaylist( playlist_display_name, PLAYLISTS_GOOD_ITEMS[PLAYLISTS_GOOD.index(playlist)])
    
    return False


def main():

    print ("")

    global ARG_CLEAN, ARG_DRYRUN

    # Check for any arguments.
    if len(sys.argv) > 1:
        for x in sys.argv:
            if x == "clean":
                ARG_CLEAN = True
                print ("========================================")
                print ("Clean argument detected, just removing playlists.")
                print ("========================================")
            if x == "dryrun":
                ARG_DRYRUN = True
                print ("========================================")
                print ("Dry run, will not modify playlists.")
                print ("========================================")

    if PLEXAPI_CHECK_204:
        print ("PlexAPI version is <= 4.1.2, will ignore status code 204 when deleting.")
        print ("For details:\nhttps://github.com/pkkid/python-plexapi/pull/580\n")


    if init_users():
        return
    if init_playlists():
        return
    if handle_playlists():
        return

    return

if __name__ == "__main__":
    main()
    print ("========================================")
    print("Done.")
    
