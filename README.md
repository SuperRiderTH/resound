# Resound
A Python script to copy playlists between users for Plex Media Server.

## How to run
Requirements: plexapi, requests, xmltodict
* Copy resound.py to your Plex server.
* Edit PLEX_TOKEN to contain the token for the owner of the server.
* (Optional) Add users to USER_WHITELIST if you wish to only sync specific users.
* (Optional) Change INCLUDE_SERVER_OWNER to False if you do not want to include the server owner in the sync.
* Run `resound.py` with Python 3.

By default, playlists that start with `!` are ignored in the sync process, but all the characters used are configurable.

## Arguments
There are optional arguments you can also use with Resound.
* `clean` - Removes any synced playlists, and does not create any new ones.
* `dryrun` - Does a dry run of the script, showing what it would do, without modifying any playlists.

Example: `python3 resound.py clean`

## Preview

![Terminal Output Preview](https://i.imgur.com/K7wvimp.png)
![Plexamp Preview](https://i.imgur.com/V6bcr63.jpg)
