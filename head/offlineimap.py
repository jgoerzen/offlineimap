#!/usr/bin/python2.2

# Copyright (C) 2002 John Goerzen
# <jgoerzen@complete.org>
#
#    This program is free software; you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation; either version 2 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program; if not, write to the Free Software
#    Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

from offlineimap import imaplib, imaputil, imapserver, repository, folder, mbnames
import re, os, os.path, offlineimap, sys
from ConfigParser import ConfigParser

# imaplib.Debug = 5

ui = offlineimap.ui.TTY.TTYUI()
ui.init_banner()

config = ConfigParser()
configfilename = os.path.expanduser("~/.offlineimaprc")
if not os.path.exists(configfilename):
    sys.stderr.write(" *** Config file %s does not exist; aborting!\n" % configfilename)
    sys.exit(1)
    
config.read(configfilename)

metadatadir = os.path.expanduser(config.get("general", "metadata"))
if not os.path.exists(metadatadir):
    os.mkdir(metadatadir, 0700)

accounts = config.get("general", "accounts")
accounts = accounts.replace(" ", "")
accounts = accounts.split(",")

server = None
remoterepos = None
localrepos = None

def syncitall():
    mailboxes = []
    for accountname in accounts:
        ui.acct(accountname)
        accountmetadata = os.path.join(metadatadir, accountname)
        if not os.path.exists(accountmetadata):
            os.mkdir(accountmetadata, 0700)
        host = config.get(accountname, "remotehost")
        user = config.get(accountname, "remoteuser")
        port = None
        if config.has_option(accountname, "remoteport"):
            port = config.getint(accountname, "remoteport")
        password = None
        if config.has_option(accountname, "remotepass"):
            password = config.get(accountname, "remotepass")
        else:
            password = ui.getpass(accountname, host, port, user)
            # Save it for future reference.
            config.set(accountname, "remotepass", password)
        ssl = config.getboolean(accountname, "ssl")

        # Connect to the remote server.
        server = imapserver.IMAPServer(user, password, host, port, ssl)
        remoterepos = repository.IMAP.IMAPRepository(config, accountname, server)

        # Connect to the Maildirs.
        localrepos = repository.Maildir.MaildirRepository(os.path.expanduser(config.get(accountname, "localfolders")))

        # Connect to the local cache.
        statusrepos = repository.LocalStatus.LocalStatusRepository(accountmetadata)

        ui.syncfolders(remoterepos, localrepos)
        remoterepos.syncfoldersto(localrepos)

        for remotefolder in remoterepos.getfolders():
            mailboxes.append({'accountname': accountname,
                              'foldername': remotefolder.getvisiblename()})
            # Load local folder.
            localfolder = localrepos.getfolder(remotefolder.getvisiblename())
            if not localfolder.isuidvalidityok(remotefolder):
                ui.validityproblem(remotefolder)
                continue
            ui.syncingfolder(remoterepos, remotefolder, localrepos, localfolder)
            ui.loadmessagelist(localrepos, localfolder)
            localfolder.cachemessagelist()
            ui.messagelistloaded(localrepos, localfolder, len(localfolder.getmessagelist().keys()))

            # Load remote folder.
            ui.loadmessagelist(remoterepos, remotefolder)
            remotefolder.cachemessagelist()
            ui.messagelistloaded(remoterepos, remotefolder,
                                 len(remotefolder.getmessagelist().keys()))

            # Load status folder.
            statusfolder = statusrepos.getfolder(remotefolder.getvisiblename())
            statusfolder.cachemessagelist()

            #

            if not statusfolder.isnewfolder():
                # Delete local copies of remote messages.  This way,
                # if a message's flag is modified locally but it has been
                # deleted remotely, we'll delete it locally.  Otherwise, we
                # try to modify a deleted message's flags!  This step
                # need only be taken if a statusfolder is present; otherwise,
                # there is no action taken *to* the remote repository.

                remotefolder.syncmessagesto_delete(localfolder, [localfolder,
                                                                 statusfolder])
                ui.syncingmessages(localrepos, localfolder, remoterepos, remotefolder)
                localfolder.syncmessagesto(statusfolder, [remotefolder, statusfolder])

            # Synchronize remote changes.
            ui.syncingmessages(remoterepos, remotefolder, localrepos, localfolder)
            remotefolder.syncmessagesto(localfolder)

            # Make sure the status folder is up-to-date.
            ui.syncingmessages(localrepos, localfolder, statusrepos, statusfolder)
            localfolder.syncmessagesto(statusfolder)
            statusfolder.save()
        server.close()


    mbnames.genmbnames(config, mailboxes)

syncitall()
if config.has_option('general', 'autorefresh'):
    refreshperiod = config.getint('general', 'autorefresh') * 60
    while 1:
        sleepamount = refreshperiod
        abortsleep = 0
        while sleepamount > 0 and not abortsleep:
            abortsleep = ui.sleeping(1, sleepamount)
            sleepamount -= 1
        ui.sleeping(0, 0)        # Done sleeping.
        syncitall()
        
