# Copyright (C) 2007, Eduardo Silva <edsiper@gmail.com>.
# Copyright (C) 2008, One Laptop Per Child
# Copyright (C) 2009, Ben Schwartz <bens@alum.mit.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import os

import logging
from gettext import gettext

import gtk
import dbus

from sugar.activity import activity
import os.path

import telepathy
import subprocess

import signal

SERVICE = 'org.sugarlabs.WatchMe'
IFACE = SERVICE
PATH = '/org/sugarlabs/WatchMe'

class WatchMeActivity(activity.Activity):

    def __init__(self, handle):
        activity.Activity.__init__(self, handle)
        
        self._logger = logging.getLogger('watchme-activity')
        self._logger.debug('Starting the WatchMe activity')
        
        self.set_title(gettext('WatchMe Activity'))
        
        self._vncdaemon = None
        self._vncviewer = None
        
        if not self._shared_activity: #I am the initiator
            toolbox = activity.ActivityToolbox(self)
            activity_toolbar = toolbox.get_activity_toolbar()
            activity_toolbar.keep.props.visible = False

            self.set_toolbox(toolbox)
            toolbox.show()
            
            self._label = gtk.Label(gettext("If you want people to be able to see everything on your screen, invite them to this activity"))

            self._connected = True
            # The initiator is "connected" without actually connecting to the VNC
            # server, because they are looking at the X server.
            self.connect('shared', self._shared_cb)
        else: # I am joining
            #A GUI is not created for a joiner.  Hopefully, the vncviewer window
            #will be the first window created by the activity, and so will get
            #a working icon, etc.
            self._label = gtk.Label(gettext("Please wait while you are connected to the shared session"))
            self._connected = False
            if self.get_shared(): #Already joined for some reason
                self._joined_cb()
            else:
                self.connect('joined', self._joined_cb)
        self.set_canvas(self._label)
        self.show_all()

    def _sharing_setup(self):
        params = {} #could be used in the future to indicate a reflector
        
        bundle_path = activity.get_bundle_path()
        port = 5900
        # Start a VNC daemon at an automatically located free TCP port,
        # scaling down by a factor of 2 with no blending (for efficiency)
        # allowing viewers to view only, not control the cursor or keyboard
        # allowing multiple viewers to join
        # continue running indefinitely
        # allow connections only from localhost
        try:
            self._vncdaemon = subprocess.Popen(['x11vnc', #search the PATH
                             '-autoport',str(port), 
                             '-viewonly',
                             '-shared',
                             '-forever',
                             '-localhost'], stdout=subprocess.PIPE)
            # When run with -autoport, x11vnc finds an open port, opens it, and
            # prints a line of the form
            # PORT=5972
            # to stdout.
            x = self._vncdaemon.stdout.readline()
            success = 'PORT='
            if x[:len(success)] == success:
                port = int(x[len(success):])
                logging.debug('started VNC daemon successfully on port %d' % port)
            else:
                self._vncdaemon.terminate()
                self._vncdaemon.wait()
                self._logger.error('unable to find an open port!')
                self.close()
            return (params, port)
        except OSError:
            self._label.set_text("x11vnc is required, but not properly installed. Please install x11vnc and restart this activity.")
            return (None, None)
        

    def _shared_cb(self, activity):
        self._logger.debug('My activity was shared')
        self.initiating = True
        (params, port) = self._sharing_setup()

        if port is not None:
            self._logger.debug('This is my activity: making a tube...')
            
            address = ('127.0.0.1', dbus.UInt16(port))
            
            tubes_chan = self._shared_activity.telepathy_tubes_chan
            id = tubes_chan[telepathy.CHANNEL_TYPE_TUBES].OfferStreamTube(
                SERVICE, params, telepathy.SOCKET_ADDRESS_TYPE_IPV4, address,
               telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0)

    def _joined_cb(self, also_self):
        tubes_chan = self._shared_activity.telepathy_tubes_chan

        tubes_chan[telepathy.CHANNEL_TYPE_TUBES].connect_to_signal('NewTube',
            self._new_tube_cb)
        tubes_chan[telepathy.CHANNEL_TYPE_TUBES].ListTubes(
            reply_handler=self._list_tubes_reply_cb,
            error_handler=self._list_tubes_error_cb)

    def _new_tube_cb(self, tube_id, initiator, tube_type, service, params, state):
        self._logger.debug('New Tube')
        if ((tube_type == telepathy.TUBE_TYPE_STREAM) and
            (service == SERVICE) and (not self._connected)):
            tubes_chan = self._shared_activity.telepathy_tubes_chan
            iface = tubes_chan[telepathy.CHANNEL_TYPE_TUBES]
            addr = iface.AcceptStreamTube(tube_id,
                       telepathy.SOCKET_ADDRESS_TYPE_IPV4,
                       telepathy.SOCKET_ACCESS_CONTROL_LOCALHOST, 0)

            port = int(addr[1])
            # additional properties are available from params

            ## Start a VNC viewer pointed at the appropriate port.
            #self._vncviewer = subprocess.Popen(['/usr/bin/vncviewer', 
            #                           'localhost::%d' % port,
            #                           '-ViewOnly',
            #                           '-Shared'])
            try:
                import gtkvnc
                vncwidget = gtkvnc.Display()
                self.set_canvas(vncwidget)
                vncwidget.realize() # I don't know what this does
                vncwidget.open_host('localhost',str(port))
                self._connected = True
                self.show_all()
            except ImportError:
                self._label.set_text("gtk-vnc-python is not properly installed.  You must install gtk-vnc-python and restart this activity.")
                
    
    def can_close(self):
        #if self._vncviewer is not None:
        #    try:
        #        os.kill(self._vncviewer.pid,signal.SIGTERM)
        #    except:
        #        pass
        #    #self._vncviewer.terminate() #requires python 2.6
        if self._vncdaemon is not None:
            try:
                os.kill(self._vncdaemon.pid,signal.SIGTERM)
            except:
                pass
            #self._vncdaemon.terminate() #requires python 2.6
        return True

    def _list_tubes_reply_cb(self, tubes):
        for tube_info in tubes:
            self._new_tube_cb(*tube_info)

    def _list_tubes_error_cb(self, e):
        self._logger.error('ListTubes() failed: %s' % e)
