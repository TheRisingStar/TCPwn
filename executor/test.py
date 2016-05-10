# Samuel Jero <sjero@purdue.edu>
# Actual strategy test routines
import manage_vms as mv
import os
import sys
import subprocess
import time
from datetime import datetime
import socket
import struct
import threading

system_home = os.path.split(os.path.dirname(os.path.realpath(__file__)))[0]
lib_path = os.path.abspath(os.path.join(system_home, 'executor', 'libs'))
config_path = os.path.abspath(os.path.join(system_home, 'config'))
proxy_path = os.path.abspath(os.path.join(system_home, 'proxy'))
log_path = os.path.abspath(os.path.join(system_home, 'logs'))
sys.path.insert(1, lib_path)
sys.path.insert(0, config_path)
import config
import spur



class CCTester:

    def __init__(self, instance, log):
        self.instance = instance
        self.clients = [instance*len(config.vm_name_bases)+1, instance*len(config.vm_name_bases)+2]
        self.servers = [instance*len(config.vm_name_bases)+3, instance*len(config.vm_name_bases)+4]
        self.tc = [instance*len(config.vm_name_bases)+5]
        self.log = log
        self.testnum = 1
        self.creating_baseline = False
        self.timers = []

    def baseline(self, test_script):
        self.creating_baseline = True
        num = self.testnum
        self.veriflow_flips = []

        # Do Baseline
        i = 0
        while i < config.stat_baseline_nrounds:
            self.testnum = 0
            print "[%s] Baseline round %d." % (str(datetime.today()), i)
            res = self.doTest(None)
            if res[0] == False:
                print "Warning!!! Baseline failed!!!"
                i += 1
        
        self.testnum = num
        self.creating_baseline = False

        # Log Thresholds
        decor = '$' * 40 + ' Thresholds ' + '$' * 40 + '\n'
        self.log.write(decor)
        self.log.write(decor)
        self.log.flush()

    def doTest(self, strategy):
        """
        :return [True | False, str]: First boolean value indicates pass or fail,
        	followed by an explanation
        """
        result = [True, "Success!"]
        self.log.write('#' * 30 + "Starting Test " + str(self.testnum) + '#' * 30 + '\n')
        self.log.write(str(datetime.today()) + "\n")

        # Start Proxy
        proxy = self._start_proxy()
        if proxy is None:
            return (False, "System Failure")

        # Send Proxy Strategy
        if self._send_proxy_strategy(strategy) == False:
            self._stop_proxy(proxy)
            return (False, "System Failure")

        # Do Test
        res = self._call_test()
        if res[0] is False:
            self._stop_proxy(proxy)
            return (False, "System Failure")

        # Evaluate Results

        # Stop Proxy
        if self._stop_proxy(proxy) == False:
            self._stop_controllers()
            return (False, "System Failure")

        # Cleanup Any Mininet Remnants
        self._cleanup()

        # Log
        self.log.flush()
        self.log.write("*****************\n")
        self.log.write("Test Result: " +
                       str(result[0]) + " , Reason:" + str(result[1]) + "\n")
        self.log.write(str(datetime.today()) + "\n")
        self.log.write("##############################Ending Test " +
                       str(self.testnum) + "###################################\n")
        self.log.flush()
        self.testnum += 1
        return result

    def startVms(self):
        for c in self.clients:
            mv.startvm(c)
        for s in self.servers:
            mv.startvm(s)
        for t in self.tc:
            mv.startvm(t)   
        for c in self.clients:
            if(self._waitListening(mv.vm2ip(c), 22, 240, True) == False):
                print "Error: Controller VM %d not started!" % (c)
                return False
        for s in self.servers:
            if(self._waitListening(mv.vm2ip(s), 22, 240, True) == False):
                print "Error: Mininet %d not started!" % (c)
                return False
        for t in self.tc:
            if(self._waitListening(mv.vm2ip(t), 22, 240, True) == False):
                print "Error: Mininet %d not started!" % (c)
                return False
            else:
                if config.vm_replace_data:
                    os.system("scp -r -p -i %s -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -r %s %s@%s:~\n" %
                              (config.vm_ssh_key, proxy_path, config.vm_user, mv.vm2ip(t)))
                    shell = spur.SshShell(hostname=mv.vm2ip(t), username=config.vm_user,
                                          missing_host_key=spur.ssh.MissingHostKey.accept, private_key_file=config.vm_ssh_key)
                    proc = shell.run(
                        ["/bin/bash", "-i", "-c", "cd proxy && make clean && make"])
                    if proc.return_code is not 0:
                        print "Error: Make failed!"
                        return False
        return True

    def stopVms(self):
        for c in self.clients:
            mv.stopvm(c)
        for s in self.servers:
            mv.stopvm(s)
        for t in self.tc:
            mv.stopvm(t)

    def _start_proxy(self):
        proxy = None
        ts = time.time()
        cmd = config.proxy_cmd.format(port=str(config.proxy_com_port))
        self.log.write("Proxy CMD: " + cmd + "\n")
        
        shell = spur.SshShell(hostname = mv.vm2ip(self.tc[0]),username = config.vm_user,
                                  missing_host_key=spur.ssh.MissingHostKey.accept, private_key_file=config.vm_ssh_key)
        try:
            ret = shell.run(["/bin/bash", "-i", "-c", config.limit_cmd])
            self.log.write("Setting up netem: " + ret.output)
        except Exception as e:
            print "Setting up netem failed: " + str(e)
            self.log.write("Setting up netem failed: " + str(e) + "\n")
            return None
        proxy = shell.spawn(["/bin/bash", "-i", "-c", cmd], store_pid=True, allow_error=True)
        if not proxy.is_running():
            res = proxy.wait_for_result()
            self.log.write("Proxy Failed to Start: " + res.output + res.stderr_output)
            return None
        else:
            self.log.write("Started proxy on " + str(mv.vm2ip(self.tc[0]))+ "...")

        if(self._waitListening(mv.vm2ip(self.tc[0]), config.proxy_com_port, 240, True) == False):
            self.log.write("Proxy Failed to start after 240 seconds!\n")
            print "Proxy Failed to Start after 240 seconds!"
            return None
        self.log.write('[timer] Start proxy: %f sec.\n' % (time.time() - ts))
        self.proxy_running = True
        return proxy

    def _call_test(self):
        ts = time.time()

        #Start servers
        for s in self.servers:
            shell = spur.SshShell(hostname=mv.vm2ip(s), username=config.vm_user,
                              missing_host_key=spur.ssh.MissingHostKey.accept, private_key_file=config.vm_ssh_key)
            try:
                ret = shell.run(["/bin/bash", "-i", "-c", config.server_start_cmd])
            except Exception as e:
                print "Failed to start server"
                self.log.write("Failed to start server\n")
                return False,0
        self.log.write("Servers Started...\n")

        #Start background traffic
        shell = spur.SshShell(hostname=mv.vm2ip(self.clients[1]), username=config.vm_user,
                              missing_host_key=spur.ssh.MissingHostKey.accept, private_key_file=config.vm_ssh_key)
        background = shell.spawn(["/bin/bash", "-i", "-c", config.background_client_cmd],store_pid=True,allow_error=True)
        if not background.is_running():
            ret = background.wait_for_result()
            print "Background traffic command failed: %s %s" % (ret.output, ret.stderr_output)
            self.log.write("Background traffic command failed: %s %s\n" % (ret.output, ret.stderr_output))
            return False,0

        #Start main traffic
        shell = spur.SshShell(hostname=mv.vm2ip(self.clients[0]), username=config.vm_user,
                              missing_host_key=spur.ssh.MissingHostKey.accept, private_key_file=config.vm_ssh_key)
        mts = time.time()
        ret = None
        try:
            ret = shell.run(["/bin/bash", "-i", "-c", config.main_client_cmd])
        except Exception as e:
            print "Main Traffic Command failed: " + str(e)
            self.log.write("Main Traffic Command Failed: " + str(e) + "\n")
            background.send_signal(2)
            return False,0
        speed = time.time() - mts
        self.log.write("Main Traffic command output: %s\n" %(ret.output))

        #Wait for background traffic to finish
        while background.is_running():
              time.sleep(0.5)
        self.log.write("Background Traffic command output: %s\n" %(background.wait_for_result().output))
        return True, speed

    def _stop_proxy(self, proxy):
        if self.proxy_running is False:
            return True
        ts = time.time()
        if not proxy.is_running():
            print "Proxy has crashed!!!\n"
            self.log.write("Proxy has crashed!!!\n")
            self.log.flush()
            return False
        proxy.send_signal(2)
        ret = proxy.wait_for_result()
        self.log.write("***** Proxy Output*****\n")
        self.log.write(ret.output)
        self.log.write(ret.stderr_output)
        self.log.flush()
        self.log.write('[timer] Stop proxy: %f sec.\n' % (time.time() - ts))
        self.proxy_running = False
        return True

    def _cleanup(self):
        ts = time.time()
        self.log.write('[timer] Clean up: %f sec.\n' % (time.time() - ts))
        return True

    def _send_proxy_strategy(self, strategy):
        strat = ""
        # Default strategy
        if strategy == None:
            strategy = ["*,*,TCP,0,0,CLEAR,*"]
        ts = time.time()

        for l in strategy:
            if type(l) is dict:
                if 'action' not in l:
                    return False
                strat = l['action']
                if 'time' in l and l['time'] > 0.01:
                    strat = dict(l)
                    strat['time'] = 0
                    tmr = threading.Timer(l['time'], self._send_proxy_strategy, [[strat],proxyaddrs])
                    tmr.start()
                    self.timers.append(tmr)
                    continue
            elif type(l) is str:
                strat = l
            else:
                return False
            self.log.write("Strategy CMD: " + strat + "\n")
            self.log.flush()
            for t in self.tc:
                res = self._proxy_communicate((mv.vm2ip(t), config.proxy_com_port), strat)
                if (res == False):
                    self.log.write("Failed to Send Command\n")
                    self.log.flush()
                    return False
        self.log.write('[timer] Send strategy: %f sec.\n' % (time.time() - ts))
        return True

    def _waitListening(self, host='127.0.0.1', port=80, timeout=None, output=False):
        """Wait until server is listening on port.
        returns True if server is listening"""
        cmd = ('echo A | telnet -e A %s %s' % (host, port))
        start = time.time()
        result = ""
        try:
            result = subprocess.check_output(
                cmd, shell=True, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as e:
            pass
        while 'Connected' not in result:
            if 'No route' in result:
                return False
            if timeout and time.time() >= start + timeout:
                print 'could not connect to %s on port %d' % (host, port)
                return False
            if output:
                print 'waiting for ' + host + ' to listen on port ' + str(port)
            time.sleep(0.5)
            try:
                result = subprocess.check_output(
                    cmd, shell=True, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                pass
        if output:
            print host + " is listening on " + str(port)
            return True

    def _proxy_communicate(self, addr, msg, wait_for_response=False):
        rsp = ""

        # Connect
        try:
            sock = socket.create_connection(addr)
        except Exception as e:
            self.log.write(
                "Failed to connect to to proxy(%s:%d): %s\n" % (addr[0], addr[1], e))
            self.log.flush()
            return False

        # Buid command
        snd = struct.pack("!H", len(msg) + 2)
        snd += msg

        # Send command
        sock.send(snd)

        if wait_for_response:
            # Wait for Length
            data = ""
            while (len(data) < 3):
                data = sock.recv(4, socket.MSG_PEEK)
                if len(data) == 0:
                    sock.close()
                    return False

            # compute length
            try:
                length = struct.unpack("!H", data[0:2])
                length = length[0]
            except Exception as e:
                sock.close()
                return False

            # Receive Message
            msg = ""
            mlen = length
            while(len(msg) < mlen):
                data = sock.recv(length)
                if len(data) == 0:
                    sock.close()
                    return False
                msg += data
                length -= len(data)

            # Process Message
            rsp = msg[2:]

        # Close Socket
        sock.close()
        if wait_for_response:
            return rsp
        return True