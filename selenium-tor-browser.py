#!/usr/bin/env python
# -*- mode: python ; coding: utf-8 -*-

"""selenium-tor-browser - Drive a TorBrowser with Selenium.

Made with Selenium-2.37.2 on Python-2.7.5+.

This script was made in order to test running a TorBrowser within a
pypy-c-sandbox, in order to see if the syscall shim in Pypy's sandbox is still
utilised for a launched Firefox subprocess.

** Building Pypy with a tracing-JIT and sandbox, and running this script: **

My copy of pypy-c-sandbox was created by building pypy from source_, then
using the built pypy to translate_ another pypy (in order to get the sandbox
and the tracing JIT) with the following options:

    ∃!isisⒶwintermute:(master *$)~/code/sources/pypy/pypy/goal ∴ pypy-c \
    …  ../../rpython/bin/rpython --output=pypy-c-sandbox \
    …  -Ojit --sandbox targetpypystandalone

Then the resulting ``pypy-c-sandbox`` was packaged_ in the normal way, by
doing:

    ∃!isisⒶwintermute:(master *$)~/code/sources/pypy/pypy/tool/release ∴ python \
    …  package.py ../../.. pypy-sandbox-JIT-2.2.0-alpha0

Then, the package, ``pypy-sandbox-JIT-2.2.0-alpha0.tar.gz`` was installed in
``/opt/`` and symbolically linked to ``/usr/local/bin/``:

    ∴ sudo ln -s /opt/pypy-sandbox-JIT-2.2.0-pypy0/bin/pypy \
    …  /usr/local/bin/pypy-sandbox

Using this pypy-sandbox, a new copy of setuptools and pip were installed,
similarly symlinked, and then used to install Selenium:

    ∴ curl -O https://bitbucket.org/pypa/setuptools/raw/bootstrap/ez_setup.py
    ∴ curl -O https://raw.github.com/pypa/pip/master/contrib/get-pip.py
    ∴ sudo python ./ex_setup.py && sudo python ./get-pip.py
    ∴ sudo ln -s /opt/pypy-sandbox-JIT-2.2.0-pypy0/bin/pip \
    …  /usr/local/bin/pypy-sandbox-pip
    ∴ sudo pypy-sandbox-pip install selenium

Finally, this script was run, not with the crunchbang given, but by doing:

    ∴ pypy-sandbox ./selenium-tor-browser.py

.. _source: http://pypy.org/download.html#building-from-source
.. _translate: http://pypy.readthedocs.org/en/latest/getting-started-python.html#translating-the-pypy-python-interpreter
.. _packaged: http://pypy.org/download.html#packaging

――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――――
 :author:    Isis <isis@torproject.org> 4096R\A3ADB67A2CDB8B35
 :version:   0.0.1
 :license:   AGPLv3
 :copyright: (c)2013 Isis Agora Lovecruft
"""

from __future__ import print_function

import logging as l
import os
import socket
import sys

l.getLogger().setLevel(10)

from subprocess import PIPE

try:
    from selenium import selenium
    from selenium import webdriver
    from selenium.webdriver import firefox
    from selenium.webdriver import DesiredCapabilities

    from selenium.webdriver.common.alert import Alert
    from selenium.webdriver.common.utils import free_port

    from selenium.webdriver.firefox import extension_connection
    from selenium.webdriver.firefox.firefox_binary import FirefoxBinary

    from selenium.common.exceptions import WebDriverException
except ImportError as error:
    l.error(error.message)
    l.warn("This script requires the Python bindings for the Selenium ",
           "WebDriver, version 2.37.2 or higher.")

TBB_DIR = 'tor-browser-3.0-b1'
TBB_BINARY = os.path.join(TBB_DIR, 'Browser', 'firefox')
TBB_LOGFILE = os.path.join(TBB_DIR, 'sandboxed-tor-browser.log')
TBB_PROFILE = os.path.join(TBB_DIR, 'Data', 'Browser', 'profile.default')
TBB_EXT_DIR = os.path.join(TBB_PROFILE, 'extensions')

TORBUTTON_XPI = 'torbutton@torproject.org.xpi'
TORLAUNCHER_XPI = 'tor-launcher@torproject.org.xpi'
NOSCRIPT_XPI = '{73a6fe31-595d-460b-a920-fcc0f8843232}.xpi'

# Ugh. HTTPEverywhere is a directory.
#HTTPEVERYWHERE_XPI = os.path.join(TBB_EXT_DIR, 'https_everywhere')

CHECK_URL = 'https://check.torproject.org'


def getTBBBinary(binary=None, logfile=None):
    """Get a :class:`FirefoxBinary` pointing to the TBB firefox binary.

    :type binary: string or None
    :param binary: The path, relative or absolute, to the TBB firefox binary.
    :type logfile: string or None
    :param logfile: The path, relative or absolute, to the file to store the
        firefox browser log messages and JS addons/extension messages in.
    """
    if not binary:
        binary = TBB_BINARY
    if not logfile:
        logfile = TBB_LOGFILE

    tbbLogfile = open(logfile, 'a+')
    tbbBinary = FirefoxBinary(firefox_path=binary,
                              log_file=tbbLogfile)
    return tbbBinary


def getTBBProfile(profile_directory=None):
    """Get a :class:`FirefoxProfile` pointing to TBB's profile directory.

    :param string profile_directory: The path to TBB's profile directory.
    """
    if profile_directory is None:
        profile_directory = TBB_PROFILE
    try:
        tbbProfile = TorBrowserProfile()
    except Exception as error:
        l.error("There was an error creating the TBB FirefoxProfile instance:")
        l.error(error)
    else:
        return tbbProfile


class TorBrowserProfile(webdriver.FirefoxProfile):
    """Configuration for using TBB's extensions and profile settings."""

    def __init__(self, profile_directory=None):
        """Initialise a TBB profile.

        This will automatically choose a free port and add the TorButton,
        TorLauncher, and NoScript addons. The HTTPSEverywhere addon is not
        added because it is a directory, not an .xpi file, in TBB's profile
        directory, and thus there isn't an easy way to add it to a Selecium
        :class:`webdriver.FirefoxProfile` instance.
        """
        if profile_directory is None:
            profile_directory = TBB_PROFILE

        super(TorBrowserProfile, self).__init__(profile_directory)

        for ext in [TORBUTTON_XPI, TORLAUNCHER_XPI, NOSCRIPT_XPI]:
            self.add_extension(ext)

        self.port = free_port()

    def add_extension(self, extension=None):
        """Add extensions by appending the .xpi location to TBB_EXT_DIR."""
        if not extension:
            extension = 'webdriver.xpi'
        else:
            extension = os.path.join(TBB_EXT_DIR, extension)
        self._install_extension(extension)


class TorBrowserBinary(FirefoxBinary):
    """Used to control LD_LIBRARY_PATH settings during TBB startup."""

    NO_FOCUS_LIBRARY_NAME = 'x_ignore_nofocus.so'

    def __init__(self, firefox_path=None, log_file=None):
        if not firefox_path:
            firefox_path = TBB_BINARY

        self._start_cmd = self._get_firefox_start_cmd()
        self._log_file = log_file or PIPE

        self.command_line = None

        self._firefox_env = os.environ.copy()
        self._firefox_env['MOZ_CRASHREPORTER_DISABLE'] = '1'
        self._firefox_env['MOZ_NO_REMOTE'] = '1'
        self._firefox_env['NO_EM_RESTART'] = '1'

    def _get_firefox_start_cmd(self, profile_directory=None,
                               addStartTorBrowserArgs=True):
        """Return the command to start TorBrowser."""
        start_cmd = ''
        if sys.platform.startswith('linux') and os.path.isfile(TBB_BINARY):
            start_cmd += TBB_BINARY
        if (profile_directory is not None) and addStartTorBrowserArgs:
            start_cmd += '-no-remote -profile %s' % profile_directory

        return start_cmd

    def _find_exe_in_registry(self):
        """Override superclass method because we don't care about Windoze."""
        pass

    def _default_windows_location(self):
        """Override superclass method because we don't care about Windoze."""
        pass

    def _start_from_profile_path(self, path):
        raise NotImplemented("XXX implement me; override parent class")

    def _modify_link_library_path(self):
        LDlib = self._extract_and_check(self.profile,
                                        self.NO_FOCUS_LIBRARY_NAME,
                                        'x86',
                                        'amd64')
        LDlib += os.environ.get('LD_LIBRARY_PATH', '')

        self._firefox_env['LD_LIBRARY_PATH'] = LDlib
        self._firefox_env['LD_PRELOAD'] = self.NO_FOCUS_LIBRARY_NAME

    def _extract_and_check(self, profile, no_focus_so_name, x86, amd64):
        raise NotImplemented("XXX implement me; override parent class")

    def which(self, fname):
        raise NotImplemented("XXX implement me; override parent class")


class TorBrowserCommandExecutor(extension_connection.ExtensionConnection):
    """Used to relay commands to a TorBrowserDriver."""

    HOST = '127.0.0.1'

    def __init__(self, binary=None, logfile=None, profile_directory=None,
                 timeout=30):
        self.binary = getTBBBinary(binary, logfile)
        self.profile = getTBBProfile(profile_directory)

        # Using the usual arguments from the
        # `tor-browser_en-US/start-tor-browser` script seems to break
        # everything:
        #self.binary.add_command_line_options('-no-remote')
        #self.binary.add_command_line_options("-profile '%s'"
        #                                     % self.profile.profile_dir)

        self.profile.native_events_enabled = True

        # See https://code.google.com/p/selenium/wiki/FirefoxDriver (at the
        # very bottom of the page) for why the strategy should probably be set
        # to 'unstable'
        self.profile.set_preference('webdriver.load.strategy', 'unstable')

        # Disable TorLauncher's XUL window querying if we want to configure
        # the network settings:
        self.profile.set_preference('extensions.torlauncher.prompt_at_startup', 0)
        self.profile.set_preference('browser.startup.page', "\"about:tor\"")

        # Override Selenium reseting this:
        self.profile.set_preference('startup.homepage_welcome_url', "\"about:tor\"")
        self.profile.update_preferences()

        super(TorBrowserCommandExecutor, self).__init__(self.HOST,
                                                        self.profile,
                                                        self.binary)


class TorBrowserDriver(webdriver.Firefox, firefox.webdriver.RemoteWebDriver):
    """Selenium WebDriver for a TorBrowser.

    This defines a Selenium WebDriver_, which manipulates the browser startup
    to handle the alert series of TorLauncher's first run, as well as the
    JSONWireProtocol_ for interacting with TorBrowser version 3.0b1_.

    The Python bindings for Selenium have rather crappy docs_. They're really
    not kidding, in their official_ docs, when they say "Use the source,
    Luke!" It really is easier to just read the code. :'(

    .. _WebDriver: http://www.seleniumhq.org/docs/04_webdriver_advanced.jsp
    .. _JSONWireProtocol: https://code.google.com/p/selenium/wiki/JsonWireProtocol
    .. _3.0b1: https://archive.torproject.org/tor-package-archive/torbrowser/3.0b1/
    .. _docs: http://selenium-python.readthedocs.org/en/latest/index.html
    .. _official: https://selenium.googlecode.com/svn/trunk/docs/api/py/index.html
    """

    capabilities = DesiredCapabilities.FIREFOX
    capabilities.update({'handlesAlerts': True,
                         'databaseEnabled': True,
                         'javascriptEnabled': True,
                         'browserConnectionEnabled': True})

    def __init__(self, command_executor='http://127.0.0.1:4444/wd/hub',
                 desired_capabilities=None, browser_profile=None, proxy=None):
        """Create a Selenium TorBrowserDriver.

        :type command_executor:
            :class:`selenium.webdriver.common.command.CommandExecutor` or string
        :param command_executor: A ``CommandExecutor`` or a string specifying
            the remote server to connect to. (default:
            'http://127.0.0.1:4444/wd/hub')
        :param dict desired_capabilities: Dictionary holding predefined values
            for starting a browser.
        :type browser_profile:
            :class:`selenium.webdriver.firefox.firefox_profile.FirefoxProfile`
        :param browser_profile: A ``FirefoxProfile``.
        :param proxy: A :class:`selenium.webdriver.common.proxy.Proxy` object,
            to specify a proxy for the browser to use.
        """
        if proxy is not None:
            proxy.add_to_capabilities(self.capabilities)

        self.command_executor = TorBrowserCommandExecutor()

        # We need a way to somehow interract with the XUL popup window which
        # TorLauncher creates on startup, disabling the
        # 'extensions.torlauncher.prompt_at_startup' preference on the
        # FirefoxProfile instance causes it not to ask if we want to configure
        # network settings, however, tor seems to *always* fail to launch on
        # the first attempt, then TorLauncher creates an alert window saying
        # "tor has failed to launch". The "OK" button on this alert window
        # must be clicked manually before TBB will actually launch. Therefore,
        # the creation of the ``tbbDriver`` object cannot happen without
        # manual interaction.
        #
        # The Interwebz suggests that we try using Mozmill (a Mozilla fork of
        # the Windmill browser test automation framework). There is also
        # Mozilla's Marionette testing framework, which will allow us to
        # interact with the ``chrome://`` and XUL elements of FF addons.

        #torLauncherAlert = Alert().accept()

        super(TorBrowserDriver, self).__init__(
            command_executor=self.command_executor,
            desired_capabilities=self.capabilities)


def getDriver(profile, binary):
    """This gets us a driver without using any of the custom classes."""
    driver = None
    capabilities = DesiredCapabilities.FIREFOX
    capabilities.update({'handlesAlerts': True,
                         'databaseEnabled': True,
                         'javascriptEnabled': True,
                         'browserConnectionEnabled': True})
    binary = getTBBBinary()
    profile = webdriver.FirefoxProfile(profile_directory=TBB_PROFILE)
    try:
        driver = webdriver.Firefox(firefox_profile=profile,
                                   firefox_binary=binary,
                                   capabilities=capabilities)
        torButton = extension_connection.ExtensionConnection('127.0.0.1',
                                                             profile,
                                                             binary)
    except WebDriverException as error:
        l.error("There was an error getting the TBB webdriver:")
        l.error(error.message)
    except socket.error as skterr:
        l.error("There was an error connecting to the TBB webdriver:")
        l.error(skterr.message)
    return driver


if __name__ == "__main__":

    tbb = None

    try:
        # Ugh. The TorLauncher XUL alert window *hates* us.

        #s = selenium('127.0.0.1', 4444, getDriver(tbbProfile, tbbBinary), CHECK_URL)
        #s.set_browser_log_level('debug')
        #
        #if s.is_alert_present():
        #    print("Detected Alert!")
        #    s.select_pop_up() # need jsWindowID
        #
        #windowIDs = s.get_all_window_ids()
        #print(windowIDs)

        #cmdExec = TorBrowserCommandExecutor()
        #tbbProfile = cmdExec.profile
        #tbbBinary = cmdExec.binary
        #tbb = getDriver(tbbProfile, tbbBinary)
        #elements = tbb.find_elements()
        #print("ELEMENTS = %s" % elements)

        tbb = TorBrowserDriver()
    except Exception as error:
        l.exception(": %s" % error)

    finally:
        if tbb is not None:
            for message in tbb.get_log('browser'):
                for level, message, timestamp in message.values():
                    l.info("%d [%s] %s" % (timestamp, level, message))
            tbb.quit()
