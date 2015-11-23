#!/usr/bin/env python
# encoding: utf-8
#
# Copyright © 2014 deanishe@deanishe.net
#
# MIT Licence. See http://opensource.org/licenses/MIT
#
# Created on 2014-04-07
#

"""appscripts.py [options] [<query>]

Find and run AppleScripts for the currently active application.

Usage:
    appscripts.py [-v|-q|-d] search [<query>]
    appscripts.py [-v|-q|-d] config [<query>]
    appscripts.py [-v|-q|-d] toggle <key>
    appscripts.py [-v|-q|-d] userpaths
    appscripts.py (-h|--version)

Options:
    --version      Show version number and exit
    -h, --help     Show this message and exit
    -q, --quiet    Only show errors
    -v, --verbose  Show info messages
    -d, --debug    Show debugging message

"""

from __future__ import print_function, unicode_literals, absolute_import

import os
import shutil
import subprocess

from docopt import docopt

from workflow import Workflow, ICON_WARNING, ICON_INFO, ICON_ERROR


log = None

HELP_URL = ('https://github.com/deanishe/alfred-appscripts'
            '#alfred-appscripts-workflow')

UPDATE_SETTINGS = {
    'github_slug': 'deanishe/alfred-appscripts'
}


DEFAULT_PATHS_FILE = os.path.join(os.path.dirname(__file__),
                                  'Script Directories.default.txt')

# Acceptable extensions for AppleScripts
SCRIPT_EXTENSIONS = ['.scpt', '.applescript', '.scptd']

# Icons
ICON_UPDATE = 'icons/update-available.icns'
ICON_NO_UPDATE = 'icons/update-none.icns'
ICON_HELP = 'icons/help.icns'
ICON_RESET = 'icons/trash.icns'
ICON_ON = 'icons/toggle_on.icns'
ICON_OFF = 'icons/toggle_off.icns'

# AppleScript snippet to return `name\nbundle_id\npath` of the frontmost app
AS_ACTIVE_APP = """\
tell application "System Events"
    set appPath to (path to frontmost application)
    set posixPath to POSIX path of appPath
    set appName to name of the first process whose frontmost is true
    set bundleId to bundle identifier of (info for appPath)
    appName & return & bundleId & return & posixPath
end tell
"""

# AppleScript to open Alfred to workflow's configuration view
AS_SHOW_CONF = 'tell application "Alfred 2" to search "appscripts "'


class AppScripts(object):
    """Encapsulates the functionality of this workflow.

    Start the application with:

        wf = Workflow()
        log = wf.logger
        app = AppScripts()
        wf.run(app.run)

    """

    def __init__(self):
        """Create new ``AppScripts`` object."""
        self.wf = None
        self.args = {}
        self.search_paths_file = None
        # Attributes to back properties
        self._app_name = None
        self._app_path = None
        self._bundle_id = None

    def run(self, wf):
        """Main script entry point.

        Parse command-line arguments and calls the appropriate method.

        """

        self.wf = wf
        self.search_paths_file = wf.datafile('AppScript Directories.txt')
        if not os.path.exists(self.search_paths_file):
            log.debug('Installing default paths file...')
            shutil.copy(DEFAULT_PATHS_FILE, self.search_paths_file)

        self.args = docopt(__doc__, version=wf.version, argv=wf.args)
        log.debug('args : %r', self.args)

        if self.args.get('search'):
            return self.do_search()
        elif self.args.get('config'):
            return self.do_config()
        elif self.args.get('userpaths'):
            return self.do_userpaths()
        elif self.args.get('toggle'):
            return self.do_toggle()
        else:
            raise ValueError('Unknown action')

    # ---------------------------------------------------------
    # Application actions

    def do_search(self):
        """Main workflow action. View and filter available scripts.

        - Get frontmost app
        - Get list of scripts for that app
        - Filter list by query if there is one
        - Show list of available scripts or warning if
          none match query/were found

        """

        args = self.args
        wf = self.wf

        query = args.get('<query>')

        if wf.update_available:
            wf.add_item('A new version is available',
                        '↩ or ⇥ to install update',
                        autocomplete='workflow:update',
                        icon=ICON_UPDATE)

        try:
            scripts = self.get_scripts_for_app()
        except RuntimeError as err:
            self.show_error(str(err).decode('utf-8'))
            return 1

        if not scripts:
            self.show_warning('No scripts for {}'.format(self.app_name))
            return 0

        if query:
            scripts = wf.filter(query, scripts,
                                key=lambda t: os.path.basename(t[0]),
                                min_score=30)

        if not scripts:
            self.show_warning('No matching scripts')
            return 0

        for script, appdir in scripts:
            title = os.path.splitext(os.path.basename(script))[0]
            if appdir:
                icon_file = self.app_path
            else:
                icon_file = script
            wf.add_item(
                title,
                '↩ to run',
                arg=script,
                uid=script,
                valid=True,
                icon=icon_file,
                icontype='fileicon',
            )
        wf.send_feedback()

    def do_config(self):
        """Show configuration options."""

        args = self.args
        wf = self.wf

        query = args.get('<query>')
        options = []

        options.append(
            dict(title='Help',
                 subtitle='View workflow help in your browser',
                 autocomplete='workflow:help',
                 icon=ICON_HELP)
        )

        if wf.update_available:
            options.append(dict(title='Update Available',
                                subtitle='↩ or ⇥ to install update',
                                autocomplete='workflow:update',
                                icon=ICON_UPDATE))
        else:
            options.append(dict(title='No Update Available',
                                subtitle='↩ or ⇥ to check for update now',
                                autocomplete='workflow:update',
                                icon=ICON_NO_UPDATE))

        if wf.settings.get('recursive'):
            icon = ICON_ON
        else:
            icon = ICON_OFF
        options.append(dict(title='Search Directories Recursively',
                            subtitle='↩ to toggle recursive search',
                            valid=True,
                            arg='toggle recursive',
                            icon=icon))

        options.append(dict(title='Edit Script Directories',
                            subtitle='↩ to edit script directories',
                            arg='userpaths',
                            valid=True,
                            icon='icon.png'))

        options.append(dict(title='Reset to Defaults',
                            subtitle='↩ or ⇥ to reset workflow to defaults',
                            autocomplete='workflow:reset',
                            icon=ICON_RESET))

        if query:
            options = wf.filter(query, options,
                                key=lambda d: d.get('title', ''),
                                min_score=30)

        for opt in options:
            wf.add_item(**opt)

        wf.send_feedback()

    def do_userpaths(self):
        """Open user paths file in default app."""

        cmd = [b'open', self.search_paths_file.encode('utf-8')]
        return subprocess.call(cmd)

    def do_toggle(self):
        """Toggle setting on or off."""

        args = self.args
        wf = self.wf

        key = args.get('<key>')
        value = wf.settings.get(key)
        if value:
            wf.settings[key] = False
            status = 'off'
        else:
            wf.settings[key] = True
            status = 'on'
        print("Option '{0}' turned {1}".format(key, status))

        # Clear cached scripts
        wf.clear_cache(lambda filename: filename.startswith('appscripts-'))

        return subprocess.call([b'/usr/bin/osascript', b'-e', AS_SHOW_CONF])

    # ---------------------------------------------------------
    # Properties for active application

    @property
    def app_name(self):
        if self._app_name is None:
            self._get_frontmost_app()
        return self._app_name

    @property
    def app_path(self):
        if self._app_path is None:
            self._get_frontmost_app()
        return self._app_path

    @property
    def bundle_id(self):
        if self._bundle_id is None:
            self._get_frontmost_app()
        return self._bundle_id

    # ---------------------------------------------------------
    # Helper methods

    # def _get_frontmost_app(self):
    #     """Get name, bundle_id and path of frontmost application.

    #     Set `app_name`, `app_path` and `bundle_id` properties.

    #     Raise a `RuntimeError` if frontmost application cannot be
    #     determined.
    #     """

    #     from AppKit import NSWorkspace
    #     for app in NSWorkspace.sharedWorkspace().runningApplications():
    #         if app.isActive():
    #             self._app_name = app.localizedName()
    #             self._bundle_id = app.bundleIdentifier()
    #             self._app_path = app.bundleURL().fileSystemRepresentation()
    #             log.debug('frontmost app : %r | %r | %r',
    #                       self._app_name, self._bundle_id, self._app_path)
    #             break

    #     else:
    #         raise RuntimeError("Couldn't get frontmost application.")

    def _get_frontmost_app(self):
        """Get name, bundle_id and path of frontmost application.

        Set `app_name`, `app_path` and `bundle_id` properties.

        Raise a `RuntimeError` if frontmost application cannot be
        determined.

        """

        # cmd = [b'/usr/bin/osascript', b'-e', AS_ACTIVE_APP]
        cmd = [self.wf.workflowfile('ActiveApp')]
        proc = subprocess.Popen(cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)

        output, err = proc.communicate()

        output = self.wf.decode(output)
        err = self.wf.decode(err).strip()

        if proc.returncode != 0:
            log.error('AppleScript error : %s', err)
            raise RuntimeError('Could not get frontmost application.')

        output = self.wf.decode(output)

        app_name, bundle_id, app_path = [s.strip() for s in output.split('\r')]
        log.debug('frontmost app : %r | %r | %r',
                  app_name, bundle_id, app_path)

        self._app_name = app_name
        self._app_path = app_path
        self._bundle_id = bundle_id

    def show_error(self, title, subtitle=''):
        """Show Alfred result with error icon and send feedback."""

        self.show_message(title, subtitle, ICON_ERROR)
        self.wf.send_feedback()

    def show_warning(self, title, subtitle=''):
        """Show Alfred result with warning icon and send feedback."""

        self.show_message(title, subtitle, ICON_WARNING)
        self.wf.send_feedback()

    def show_message(self, title, subtitle='', icon=ICON_INFO):
        """Show Alfred result, but do not send feedback."""

        self.wf.add_item(title, subtitle, icon=icon)

    def get_scripts_for_app(self):
        """Return list of AppleScripts in app's script directories.

        :returns: List of paths to AppleScripts
        :rtype: ``list``

        """

        # wf.cached_data needs a bare function (no arguments), so
        # wrap the call
        def _wrapper():
            return self._get_scripts_for_app()

        return self.wf.cached_data('appscripts-{0}'.format(self.bundle_id),
                                   _wrapper, max_age=30)

    def _get_scripts_for_app(self):
        """Return list of AppleScripts in script directories.

        :returns: List of paths to AppleScripts
        :rtype: ``list`` of 2-tuples ``(path, appdir)``. ``appdir``
                indicates whether the script belongs to a specific
                application.

        """

        scripts = {}
        scriptdirs = self._load_script_directories()

        for scriptdir, appdir in scriptdirs:

            if self.wf.settings.get('recursive'):
                log.debug('Recursively loading scripts from `%s`...',
                          scriptdir)
                for root, dirnames, filenames in os.walk(scriptdir):
                    for filename in filenames:
                        ext = os.path.splitext(filename)[1]
                        if ext.lower() not in SCRIPT_EXTENSIONS:
                            continue

                        path = os.path.join(root, filename)
                        wf.logger.debug('Script : %r', path)
                        if path in scripts:
                            if appdir:
                                scripts[path] = True
                        else:
                            scripts[path] = appdir

            else:
                log.debug('Loading scripts from `%s`...', scriptdir)
                for filename in os.listdir(scriptdir):
                    ext = os.path.splitext(filename)[1]
                    if ext.lower() not in SCRIPT_EXTENSIONS:
                        continue

                    path = os.path.join(scriptdir, filename)
                    kind = ('General', 'App-specific')[appdir]
                    log.debug(' %s script : %s', kind, path)
                    if path in scripts:
                        if appdir:
                            scripts[path] = True
                    else:
                        scripts[path] = appdir

        # Sort scripts. Ensure app-specific scripts appear first.
        scripts = sorted([((1, 0)[a], os.path.basename(p), p, a)
                          for p, a in scripts.items()])
        scripts = [t[2:] for t in scripts]

        log.debug('%d scripts found for app %s', len(scripts), self.app_name)

        return scripts

    def _load_script_directories(self):
        """Read script directories from ``self.search_paths_file``

        Each path returned is a 2-tuple: ``(path, appdir)``
        ``appdir`` is a boolean indicating whether the directory
        belongs to a specific app or is a "general" script directory.

        """

        scriptdirs = []

        with open(self.search_paths_file) as fp:
            for line in fp:
                line = self.wf.decode(line).strip()
                if line == '' or line.startswith('#'):
                    continue

                appdir = False  # Whether directory belongs to a specific app
                path = os.path.expanduser(os.path.expandvars(line))

                if '{app_name}' in path or '{bundle_id}' in path:
                    appdir = True

                path = path.format(app_name=self.app_name,
                                   bundle_id=self.bundle_id)

                if not os.path.exists(path):
                    log.debug('Script directory does not exist : %s', path)
                    continue

                scriptdirs.append((path, appdir))

        return scriptdirs


if __name__ == '__main__':
    wf = Workflow(update_settings=UPDATE_SETTINGS,
                  help_url=HELP_URL)
    log = wf.logger
    app = AppScripts()
    wf.run(app.run)
