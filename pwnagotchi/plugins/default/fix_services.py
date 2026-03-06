import logging
import re
import subprocess
import time
import random
from io import TextIOWrapper
import os

import pwnagotchi
from pwnagotchi import plugins

import pwnagotchi.ui.faces as faces
from pwnagotchi.bettercap import Client

from pwnagotchi.ui.components import Text
from pwnagotchi.ui.view import BLACK
import pwnagotchi.ui.fonts as fonts
import requests


class FixServices(plugins.Plugin):
    __author__ = "jayofelony"
    __version__ = "1.0.3"
    __license__ = "GPL3"
    __description__ = "Fix blindness, firmware crashes and brain not being loaded. Auto-disables for external WiFi adapters."
    __name__ = "Fix_Services"
    __help__ = """
    Reload brcmfmac module when blindbug is detected, instead of rebooting. Adapted from WATCHDOG.
    Automatically disables itself when an external WiFi adapter is detected instead of the onboard brcmfmac chip.

    Additional fixes over stock version:
    - Fixes broken LD_PRELOAD libpcap path in pwngrid-peer.service on first load
    - Restarts pwngrid-peer after any networking recovery so it rebinds to the fresh monitor interface
    - Waits for monitor interface to be UP before restarting pwngrid-peer (no blind sleep)
    - Re-enables pwngrid advertising after pwngrid-peer restart (it starts with advertising OFF)
    - Tracks mode changes (auto/manual) via on_epoch polling and toggles advertising accordingly
    """

    # pwngrid local API base — port 8666 is hardcoded in pwngrid-peer.service and grid.py
    PWNGRID_API = "http://127.0.0.1:8666/api/v1"

    def __init__(self):
        self.options = dict()
        self.pattern = re.compile(
            r"ieee80211 phy0: brcmf_cfg80211_add_iface: iface validation failed: err=-95"
        )
        self.pattern2 = re.compile(r"wifi error while hopping to channel")
        self.pattern3 = re.compile(r"Firmware has halted or crashed")
        self.pattern4 = re.compile(r"error 400: could not find interface wlan0mon")
        self.pattern5 = re.compile(
            r"fatal error: concurrent map iteration and map write"
        )
        self.pattern6 = re.compile(r"panic: runtime error")
        self.pattern7 = re.compile(
            r"ieee80211 phy0: _brcmf_set_multicast_list: Setting allmulti failed, -110"
        )
        self.isReloadingMon = False
        self.connection = None
        self.LASTTRY = 0
        self._last_mode = None  # track mode changes via on_epoch polling
        self.is_disabled = self._check_external_adapter()

    # ------------------------------------------------------------------
    # Startup checks
    # ------------------------------------------------------------------

    def _check_external_adapter(self):
        """
        Check if an external WiFi adapter is being used instead of the onboard brcmfmac chip.
        Returns True if external adapter detected (plugin should be disabled), False otherwise.
        """
        try:
            cmd_output = subprocess.check_output(
                "ls /sys/class/net/", shell=True, text=True
            )
            interfaces = cmd_output.strip().split("\n")

            if "wlan0" in interfaces:
                try:
                    driver_path = "/sys/class/net/wlan0/device/driver"
                    if os.path.exists(driver_path):
                        driver_link = os.readlink(driver_path)
                        driver_name = os.path.basename(driver_link)

                        logging.info(
                            f"[Fix_Services] Detected WiFi driver: {driver_name}"
                        )

                        if driver_name != "brcmfmac":
                            logging.info(
                                f"[Fix_Services] External WiFi adapter detected ({driver_name}). Plugin will be disabled."
                            )
                            return True
                        else:
                            logging.info(
                                "[Fix_Services] Onboard brcmfmac detected. Plugin will remain active."
                            )
                            return False
                    else:
                        lsmod_output = subprocess.check_output(
                            "lsmod | grep brcmfmac", shell=True, text=True
                        )
                        if lsmod_output.strip():
                            logging.info(
                                "[Fix_Services] brcmfmac module detected via lsmod. Plugin will remain active."
                            )
                            return False
                        else:
                            logging.info(
                                "[Fix_Services] brcmfmac module not found. External adapter likely in use. Plugin will be disabled."
                            )
                            return True

                except subprocess.CalledProcessError:
                    logging.info(
                        "[Fix_Services] brcmfmac module not found. External adapter likely in use. Plugin will be disabled."
                    )
                    return True
                except Exception as e:
                    logging.warning(
                        f"[Fix_Services] Error checking driver: {e}. Assuming external adapter. Plugin will be disabled."
                    )
                    return True
            else:
                logging.warning(
                    "[Fix_Services] wlan0 interface not found. Plugin will be disabled."
                )
                return True

        except Exception as e:
            logging.error(
                f"[Fix_Services] Error detecting WiFi adapter: {e}. Plugin will be disabled."
            )
            return True

    def _fix_libpcap(self):
        """
        Check if the LD_PRELOAD path for libpcap in pwngrid-peer.service points
        to a file that actually exists. If not, find the real libpcap and fix the
        service file automatically — then reload systemd and restart pwngrid-peer.

        This fixes the common error:
          ERROR: ld.so: object '/usr/local/lib/libpcap.so.1' from LD_PRELOAD
                 cannot be preloaded (cannot open shared object file): ignored.

        Without libpcap loaded, pwngrid cannot inject beacon frames and peers
        will never detect each other regardless of any other fix.
        """
        import glob

        service_path = "/etc/systemd/system/pwngrid-peer.service"

        try:
            with open(service_path, "r") as f:
                content = f.read()
        except Exception as err:
            logging.error("[Fix_Services] could not read %s: %s" % (service_path, err))
            return

        match = re.search(r"LD_PRELOAD=(\S+)", content)
        if not match:
            logging.debug(
                "[Fix_Services] no LD_PRELOAD found in service file, skipping libpcap check"
            )
            return

        current_path = match.group(1)
        if os.path.exists(current_path):
            logging.debug(
                "[Fix_Services] LD_PRELOAD libpcap path is valid: %s" % current_path
            )
            return

        logging.warning(
            "[Fix_Services] LD_PRELOAD path missing: %s — searching for real libpcap"
            % current_path
        )
        candidates = (
            glob.glob("/usr/lib/*/libpcap.so.1*")
            + glob.glob("/usr/lib/libpcap.so.1*")
            + glob.glob("/usr/local/lib/libpcap.so.1*")
        )

        # prefer the actual .so.x.y.z file over symlinks
        real = next(
            (c for c in candidates if os.path.isfile(c) and not os.path.islink(c)), None
        )
        if not real:
            real = next((c for c in candidates if os.path.exists(c)), None)

        if not real:
            logging.error(
                "[Fix_Services] could not find libpcap.so.1 anywhere — peers will not work"
            )
            return

        logging.info(
            "[Fix_Services] found libpcap at %s — updating service file" % real
        )
        new_content = content.replace(
            "LD_PRELOAD=%s" % current_path, "LD_PRELOAD=%s" % real
        )

        try:
            with open(service_path, "w") as f:
                f.write(new_content)
            logging.info(
                "[Fix_Services] pwngrid-peer.service updated with correct libpcap path"
            )
            os.system("systemctl daemon-reload")
            os.system("systemctl restart pwngrid-peer")
            logging.info("[Fix_Services] pwngrid-peer restarted with correct libpcap")
        except Exception as err:
            logging.error("[Fix_Services] failed to update service file: %s" % err)

    # ------------------------------------------------------------------
    # Mode detection
    # ------------------------------------------------------------------

    def _is_auto_mode(self):
        """
        Check if pwnagotchi is running in Auto mode by reading pwnagotchi.mode.
        This is the correct way — checking for .pwnagotchi-auto file does NOT
        work because that file is deleted at boot after being read.
        Falls back to parsing recent journal entries if pwnagotchi.mode is unavailable.
        """
        try:
            return pwnagotchi.mode == pwnagotchi.AUTO_MODE
        except Exception:
            pass

        # fallback: find the most recent mode log entry
        try:
            lines = subprocess.check_output(
                ["journalctl", "-u", "pwnagotchi", "-n", "50", "--no-pager"], text=True
            )
            auto_pos = lines.rfind("entering auto mode")
            manu_pos = lines.rfind("entering manual mode")
            if auto_pos == -1 and manu_pos == -1:
                return True  # assume auto if unknown
            return auto_pos > manu_pos
        except Exception:
            return True  # assume auto if we can't tell

    # ------------------------------------------------------------------
    # pwngrid helpers
    # ------------------------------------------------------------------

    def _wait_for_interface(self, iface="wlan0mon", timeout=30):
        """
        Poll until the monitor interface exists and is UP, or timeout.
        Much better than a fixed sleep — works fast on Pi4, doesn't
        time out on slower Pi0W.
        Returns True if interface came up, False if timed out.
        """
        logging.info("[Fix_Services] waiting for %s to come up..." % iface)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                out = subprocess.check_output(
                    "ip link show %s" % iface, shell=True, stderr=subprocess.DEVNULL
                ).decode()
                if "UP" in out:
                    logging.info("[Fix_Services] %s is UP" % iface)
                    return True
            except subprocess.CalledProcessError:
                pass  # interface doesn't exist yet
            time.sleep(1)
        logging.warning(
            "[Fix_Services] timeout waiting for %s — continuing anyway" % iface
        )
        return False

    def _wait_for_pwngrid_api(self, timeout=30):
        """
        Poll until the pwngrid-peer local API is accepting connections.
        Port 8666 is hardcoded in jayofelony's pwngrid-peer.service and grid.py.
        Any HTTP response (including 404) means the server is up.
        Returns True if API responded, False if timed out.
        """
        url = "%s/mesh/peers" % self.PWNGRID_API
        logging.info("[Fix_Services] waiting for pwngrid-peer API on 127.0.0.1:8666...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                requests.get(url, timeout=2)
                logging.info("[Fix_Services] pwngrid-peer API is up")
                return True
            except requests.exceptions.ConnectionError:
                pass  # server not up yet
            except Exception:
                # any other response (404 etc) means the server IS up
                logging.info("[Fix_Services] pwngrid-peer API is up")
                return True
            time.sleep(1)
        logging.warning(
            "[Fix_Services] timeout waiting for pwngrid-peer API — continuing anyway"
        )
        return False

    def _enable_advertising(self):
        """
        Enable pwngrid advertising — ONLY in Auto mode.

        Correct endpoint: GET /api/v1/mesh/advertise/true
        (mirrors grid.py: call("/mesh/advertise/true"))

        pwngrid-peer starts fresh with advertising OFF, so we must
        explicitly enable it or peers will never see us.
        """
        if not self._is_auto_mode():
            logging.info(
                "[Fix_Services] skipping pwngrid advertising — not in Auto mode"
            )
            return
        try:
            r = requests.get("%s/mesh/advertise/true" % self.PWNGRID_API, timeout=5)
            logging.info(
                "[Fix_Services] pwngrid advertising enabled (status %d)" % r.status_code
            )
        except Exception as err:
            logging.error(
                "[Fix_Services] failed to enable pwngrid advertising: %s" % err
            )

    def _disable_advertising(self):
        """
        Disable pwngrid advertising — called when switching to Manual mode.

        Correct endpoint: GET /api/v1/mesh/advertise/false
        (mirrors grid.py: call("/mesh/advertise/false"))
        """
        try:
            r = requests.get("%s/mesh/advertise/false" % self.PWNGRID_API, timeout=5)
            logging.info(
                "[Fix_Services] pwngrid advertising disabled (status %d)"
                % r.status_code
            )
        except Exception as err:
            logging.error(
                "[Fix_Services] failed to disable pwngrid advertising: %s" % err
            )

    def _restart_pwngrid(self, reason=""):
        """
        Full pwngrid-peer recovery sequence:
          1. Wait for wlan0mon to be UP        (_wait_for_interface)
          2. Restart pwngrid-peer              (rebinds to fresh interface)
          3. Wait for the pwngrid API to respond
          4. Re-enable advertising if in Auto  (_enable_advertising)

        Without step 4 the unit restarts correctly but stays invisible to
        other pwnagotchis because advertising is off after every fresh start.
        """
        self._wait_for_interface("wlan0mon")
        logging.info(
            "[Fix_Services] restarting pwngrid-peer%s"
            % (" (%s)" % reason if reason else "")
        )
        os.system("systemctl restart pwngrid-peer")
        self._wait_for_pwngrid_api()
        self._enable_advertising()
        logging.info("[Fix_Services] pwngrid-peer recovery complete")

    # ------------------------------------------------------------------
    # Plugin events
    # ------------------------------------------------------------------

    def on_loaded(self):
        if self.is_disabled:
            logging.info(
                "[Fix_Services] plugin loaded but disabled due to external WiFi adapter."
            )
            return
        logging.info("[Fix_Services] plugin loaded.")
        # Fix broken libpcap LD_PRELOAD path in pwngrid-peer.service on first run.
        # Without libpcap, pwngrid cannot inject beacon frames and peers never work.
        self._fix_libpcap()

    def on_ready(self, agent):
        if self.is_disabled:
            return
        last_lines = "".join(
            list(
                TextIOWrapper(
                    subprocess.Popen(
                        ["journalctl", "-n10", "-k"], stdout=subprocess.PIPE
                    ).stdout
                )
            )[-10:]
        )
        try:
            cmd_output = subprocess.check_output("ip link show wlan0mon", shell=True)
            logging.debug("[Fix_Services ip link show wlan0mon]: %s" % repr(cmd_output))
            if ",UP," in str(cmd_output):
                logging.debug("wlan0mon is up.")

        except Exception as err:
            logging.error("[Fix_Services ip link show wlan0mon]: %s" % repr(err))
            try:
                self._tryTurningItOffAndOnAgain(agent)
            except Exception as err:
                logging.error("[Fix_Services OffNOn]: %s" % repr(err))

        # Ensure advertising matches current mode on startup.
        # _enable_advertising() checks _is_auto_mode() internally.
        self._wait_for_pwngrid_api()
        self._enable_advertising()

    def on_epoch(self, agent, epoch, epoch_data):
        if self.is_disabled:
            return

        # Detect mode changes by polling _is_auto_mode() every epoch.
        # on_manual_mode / on_auto_mode don't exist as plugin events in this
        # codebase — mode switching restarts the process, so we track it here.
        current_mode = "auto" if self._is_auto_mode() else "manual"
        if self._last_mode != current_mode:
            logging.info(
                "[Fix_Services] mode changed: %s → %s" % (self._last_mode, current_mode)
            )
            self._last_mode = current_mode
            if current_mode == "auto":
                self._wait_for_pwngrid_api()
                self._enable_advertising()
            else:
                self._disable_advertising()

        last_lines = "".join(
            list(
                TextIOWrapper(
                    subprocess.Popen(
                        ["journalctl", "-n10", "-k"], stdout=subprocess.PIPE
                    ).stdout
                )
            )[-10:]
        )
        other_last_lines = "".join(
            list(
                TextIOWrapper(
                    subprocess.Popen(
                        ["journalctl", "-n10"], stdout=subprocess.PIPE
                    ).stdout
                )
            )[-10:]
        )
        other_other_last_lines = "".join(
            list(
                TextIOWrapper(
                    subprocess.Popen(
                        ["tail", "-n10", "/etc/pwnagotchi/log/pwnagotchi.log"],
                        stdout=subprocess.PIPE,
                    ).stdout
                )
            )[-10:]
        )
        logging.debug("[Fix_Services]**** epoch")
        if time.time() - self.LASTTRY > 180:
            display = agent.view()

            logging.debug("[Fix_Services]**** checking")
            if len(self.pattern.findall(last_lines)) >= 1:
                subprocess.check_output("monstop", shell=True)
                subprocess.check_output("monstart", shell=True)
                display.set("status", "Wifi channel stuck. Restarting recon.")
                display.update(force=True)
                pwnagotchi.restart("AUTO")

            elif len(self.pattern2.findall(other_last_lines)) >= 5:
                logging.debug(
                    "[Fix_Services]**** Should trigger a reload of the wlan0mon device:\n%s"
                    % last_lines
                )
                if hasattr(agent, "view"):
                    display.set("status", "Wifi channel stuck. Restarting recon.")
                    display.update(force=True)
                logging.debug("[Fix_Services] Wifi channel stuck. Restarting recon.")

                try:
                    result = agent.run("wifi.recon off; wifi.recon on")
                    if result["success"]:
                        logging.debug("[Fix_Services] wifi.recon flip: success!")
                        if display:
                            display.update(
                                force=True,
                                new_data={
                                    "status": "Wifi recon flipped!",
                                    "face": faces.COOL,
                                },
                            )
                        else:
                            print("Wifi recon flipped\nthat was easy!")
                    else:
                        logging.warning(
                            "[Fix_Services] wifi.recon flip: FAILED: %s" % repr(result)
                        )

                except Exception as err:
                    logging.error("[Fix_Services wifi.recon flip] %s" % repr(err))

            elif len(self.pattern3.findall(other_last_lines)) >= 1:
                logging.debug(
                    "[Fix_Services] Firmware has halted or crashed. Restarting wlan0mon."
                )
                if hasattr(agent, "view"):
                    display.set(
                        "status", "Firmware has halted or crashed. Restarting wlan0mon."
                    )
                    display.update(force=True)
                try:
                    cmd_output = subprocess.check_output("monstart", shell=True)
                    logging.debug("[Fix_Services monstart]: %s" % repr(cmd_output))
                    self._restart_pwngrid("firmware crash recovery")
                except Exception as err:
                    logging.error("[Fix_Services monstart]: %s" % repr(err))

            elif len(self.pattern4.findall(other_other_last_lines)) >= 3:
                logging.debug("[Fix_Services] wlan0 is down!")
                if hasattr(agent, "view"):
                    display.set("status", "Restarting wlan0 now!")
                    display.update(force=True)
                try:
                    cmd_output = subprocess.check_output("monstart", shell=True)
                    logging.debug("[Fix_Services monstart]: %s" % repr(cmd_output))
                    self._restart_pwngrid("interface down recovery")
                except Exception as err:
                    logging.error("[Fix_Services monstart]: %s" % repr(err))

            elif len(self.pattern5.findall(other_other_last_lines)) >= 1:
                logging.debug("[Fix_Services] Bettercap has crashed!")
                if hasattr(agent, "view"):
                    display.set("status", "Restarting pwnagotchi!")
                    display.update(force=True)
                os.system("systemctl restart bettercap")
                self._restart_pwngrid("bettercap map crash recovery")
                pwnagotchi.restart("AUTO")

            elif len(self.pattern6.findall(other_other_last_lines)) >= 1:
                logging.debug("[Fix_Services] Bettercap has crashed!")
                if hasattr(agent, "view"):
                    display.set("status", "Restarting pwnagotchi!")
                    display.update(force=True)
                os.system("systemctl restart bettercap")
                self._restart_pwngrid("bettercap panic crash recovery")
                pwnagotchi.restart("AUTO")

            elif len(self.pattern7.findall(other_other_last_lines)) >= 1:
                logging.debug("[Fix_Services] Monitor mode failed!")
                try:
                    result = agent.run("wifi.recon off; wifi.recon on")
                    if result["success"]:
                        logging.debug("[Fix_Services] wifi.recon flip: success!")
                        if display:
                            display.update(
                                force=True,
                                new_data={
                                    "status": "Wifi recon flipped!",
                                    "face": faces.COOL,
                                },
                            )
                        else:
                            print("Wifi recon flipped\nthat was easy!")
                    else:
                        logging.warning(
                            "[Fix_Services] wifi.recon flip: FAILED: %s" % repr(result)
                        )

                except Exception as err:
                    logging.error("[Fix_Services wifi.recon flip] %s" % repr(err))
            else:
                print("logs look good")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def logPrintView(self, level, message, ui=None, displayData=None, force=True):
        try:
            if level == "error":
                logging.error(message)
            elif level == "warning":
                logging.warning(message)
            elif level == "debug":
                logging.debug(message)
            else:
                logging.debug(message)

            if ui:
                ui.update(force=force, new_data=displayData)
            elif displayData and "status" in displayData:
                print(displayData["status"])
            else:
                print("[%s] %s" % (level, message))
        except Exception as err:
            logging.error("[logPrintView] ERROR %s" % repr(err))

    def _tryTurningItOffAndOnAgain(self, connection):
        if self.is_disabled:
            return
        if self.isReloadingMon and (time.time() - self.LASTTRY) < 180:
            logging.debug("[Fix_Services] Duplicate attempt ignored")
        else:
            self.isReloadingMon = True
            self.LASTTRY = time.time()

            if hasattr(connection, "view"):
                display = connection.view()
                if display:
                    display.update(
                        force=True,
                        new_data={
                            "status": "I'm blind! Try turning it off and on again",
                            "face": faces.BORED,
                        },
                    )
            else:
                display = None

            try:
                cmd_output = subprocess.check_output(
                    "ip link show wlan0mon", shell=True
                )
                logging.debug(
                    "[Fix_Services ip link show wlan0mon]: %s" % repr(cmd_output)
                )
                if ",UP," in str(cmd_output):
                    logging.debug("wlan0mon is up. Skip reset?")
            except Exception as err:
                logging.error("[Fix_Services ip link show wlan0mon]: %s" % repr(err))

            try:
                result = connection.run("wifi.recon off")
                if "success" in result:
                    self.logPrintView(
                        "info",
                        "[Fix_Services] wifi.recon off: %s!" % repr(result),
                        display,
                        {"status": "Wifi recon paused!", "face": faces.COOL},
                    )
                    time.sleep(2)
                else:
                    self.logPrintView(
                        "warning",
                        "[Fix_Services] wifi.recon off: FAILED: %s" % repr(result),
                        display,
                        {
                            "status": "Recon was busted (probably)",
                            "face": random.choice((faces.BROKEN, faces.DEBUG)),
                        },
                    )
            except Exception as err:
                logging.error("[Fix_Services wifi.recon off] error  %s" % (repr(err)))

            logging.debug("[Fix_Services] recon paused. Now trying wlan0mon reload")

            try:
                cmd_output = subprocess.check_output("monstop", shell=True)
                self.logPrintView(
                    "info",
                    "[Fix_Services] wlan0mon down and deleted: %s" % cmd_output,
                    display,
                    {"status": "wlan0mon d-d-d-down!", "face": faces.BORED},
                )
            except Exception as nope:
                logging.error("[Fix_Services delete wlan0mon] %s" % nope)
                pass

            logging.debug("[Fix_Services] Now trying modprobe -r")

            tries = 1
            while tries < 3:
                try:
                    cmd_output = subprocess.check_output(
                        "sudo modprobe -r brcmfmac", shell=True
                    )
                    self.logPrintView(
                        "info",
                        "[Fix_Services] unloaded brcmfmac",
                        display,
                        {"status": "Turning it off #%s" % tries, "face": faces.SMART},
                    )

                    try:
                        cmd_output = subprocess.check_output(
                            "sudo modprobe brcmfmac", shell=True
                        )
                        self.logPrintView("info", "[Fix_Services] reloaded brcmfmac")

                        try:
                            cmd_output = subprocess.check_output("monstart", shell=True)
                            self.logPrintView(
                                "info",
                                "[Fix_Services interface add wlan0mon worked #%s: %s"
                                % (tries, cmd_output),
                            )
                            try:
                                result = connection.run("set wifi.interface wlan0mon")
                                if "success" in result:
                                    logging.debug(
                                        "[Fix_Services set wifi.interface wlan0mon worked!"
                                    )
                                    # Restart pwngrid-peer so it rebinds to the fresh monitor interface.
                                    # Without this, pwngrid keeps injecting beacons onto the old dead
                                    # interface handle and peers are never detected.
                                    self._restart_pwngrid("brcmfmac reload")
                                    break
                                else:
                                    logging.debug(
                                        "[Fix_Services set wifi.interfaceface wlan0mon] failed? %s"
                                        % repr(result)
                                    )
                            except Exception as err:
                                logging.debug(
                                    "[Fix_Services set wifi.interface wlan0mon] except: %s"
                                    % repr(err)
                                )
                        except Exception as cerr:
                            if not display:
                                print(
                                    "failed loading wlan0mon attempt #%s: %s"
                                    % (tries, repr(cerr))
                                )
                    except Exception as err:
                        if not display:
                            print("Failed reloading brcmfmac")
                        logging.error(
                            "[Fix_Services] Failed reloading brcmfmac %s" % repr(err)
                        )

                except Exception as nope:
                    logging.error(
                        "[Fix_Services #%s modprobe -r] %s" % (tries, repr(nope))
                    )
                    if not display:
                        print("[Fix_Services #%s modprobe -r] %s" % (tries, repr(nope)))
                    pass

                tries = tries + 1
                if tries < 3:
                    logging.debug(
                        "[Fix_Services] wlan0mon didn't make it. trying again"
                    )
                    if not display:
                        print(" wlan0mon didn't make it. trying again")
                else:
                    logging.debug(
                        "[Fix_Services] wlan0mon loading failed, no choice but to reboot .."
                    )
                    pwnagotchi.reboot()

            if tries < 3:
                if display:
                    display.update(
                        force=True,
                        new_data={
                            "status": "And back on again...",
                            "face": faces.INTENSE,
                        },
                    )
                else:
                    print("And back on again...")
                logging.debug("[Fix_Services] wlan0mon back up")
            else:
                self.LASTTRY = time.time()

            time.sleep(8 + tries * 2)
            self.isReloadingMon = False

            logging.debug("[Fix_Services] re-enable recon")
            try:
                result = connection.run("wifi.clear; wifi.recon on")

                if "success" in result:
                    if display:
                        display.update(
                            force=True,
                            new_data={
                                "status": "I can see again! (probably)",
                                "face": faces.HAPPY,
                            },
                        )
                    else:
                        print("I can see again")
                    logging.debug("[Fix_Services] wifi.recon on")
                    self.LASTTRY = time.time() + 120
                else:
                    logging.error("[Fix_Services] wifi.recon did not start up")
                    self.LASTTRY = time.time() - 300
                    self.isReloadingMon = False

            except Exception as err:
                logging.error("[Fix_Services wifi.recon on] %s" % repr(err))
                pwnagotchi.reboot()

    def on_ui_setup(self, ui):
        if self.is_disabled:
            return
        with ui._lock:
            if "position" in self.options:
                pos = self.options["position"].split(",")
                pos = [int(x.strip()) for x in pos]
            else:
                pos = (ui.width() / 2 + 35, ui.height() - 11)

            logging.debug("Got here")

    def on_ui_update(self, ui):
        if self.is_disabled:
            return
        return

    def on_unload(self, ui):
        return


# run from command line to brute force a reload
if __name__ == "__main__":
    print("Performing brcmfmac reload and restart wlan0mon in 5 seconds...")
    fb = FixServices()

    data = {
        "Message": "kernel: brcmfmac: brcmf_cfg80211_nexmon_set_channel: Set Channel failed: chspec=1234"
    }
    event = {"data": data}

    agent = Client("localhost", port=8081, username="pwnagotchi", password="pwnagotchi")

    time.sleep(2)
    print("3 seconds")
    time.sleep(3)
    fb.on_epoch(agent, event, None)
    # fb._tryTurningItOffAndOnAgain(agent)
