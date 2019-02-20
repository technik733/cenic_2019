#!/usr/bin/env python3

import paramiko
import getpass
import os
import shutil
import re
import time
import csv
import sys

print ("Brocade Access Switch Port VoIPer v1.2.1 for Python 3 2018/07/23 nhildebr")

def send_command(command, chan):
    buff = ""
    chan.send(command + "\r")
    #wait for a response
    resp = chan.recv(9999).decode("utf-8")
    buff += resp
    #wait for a prompt
    while not buff.endswith("#"):
        time.sleep(.1)
        resp = chan.recv(9999).decode("utf-8")
        buff += resp
    return buff

def disable_paging_brocade(chan):
    buff = ""
    chan.send("skip\r")
    #wait for a response
    resp = chan.recv(9999).decode("utf-8")
    buff += resp
    #wait for a prompt
    while not buff.endswith("#"):
        time.sleep(.1)
        resp = chan.recv(9999).decode("utf-8")
        buff += resp
    return buff

def disable_paging_ios(chan):
    buff = ""
    chan.send("terminal length 0\r")
    #wait for a response
    resp = chan.recv(9999).decode("utf-8")
    buff += resp
    #wait for a prompt
    while not buff.endswith("#"):
        time.sleep(.1)
        resp = chan.recv(9999).decode("utf-8")
        buff += resp
    return buff


def test_credentials():
    while True:
        buff = ""
        tacacs_pw = getpass.getpass("TACACS Password: ")
        enable_pw = getpass.getpass("Enable Password: ")

        #test tacacs credentials
        try:
            #open connection to comm-vss-g because it's a good, reliable hostname that's a good test point
            ssh_test = paramiko.SSHClient()
            ssh_test.set_missing_host_key_policy(
                paramiko.AutoAddPolicy())
            ssh_test.connect("comm-vss-g",
                password=tacacs_pw)
        except:
            print ("TACACS login failure! Try again.")
            continue

        #test enable
        channel = ssh_test.invoke_shell()
        channel.send("enable\r")
        while not channel.recv_ready():
            time.sleep(.1)
        resp = channel.recv(9999).decode("utf-8")
        buff += resp
        #the first is for brocade, the second is for cisco
        while not (resp.endswith("Password: ") or resp.endswith("Password:")):
            time.sleep(.1)
            resp = channel.recv(9999).decode("utf-8")
            buff += resp

        #send password
        channel.send(enable_pw + "\r")
        while not channel.recv_ready():
            time.sleep(.1)
        resp = channel.recv(9999).decode("utf-8")
        buff += resp
        if resp.endswith(">"):
            print ("Enable password failure! Try again.")
            continue
        while not resp.endswith("#"):
            time.sleep(.1)
            resp = channel.recv(9999).decode("utf-8")
            buff += resp

        print ("Credentials success!")
        break

    channel.close()
    return tacacs_pw, enable_pw, channel

def vlan_ports_parser(buff):
    #dump the lines into a list for easier management
    lines = buff.split("\r\n")

    #parse the existing config and store data
    #line_index= 0
    grab_ports = 0
    vlan_ports = {}
    for line in lines:

        #get rid of whitespace
        line = line.rstrip()

        #reset the port grab trigger after two lines
        if grab_ports == 3:
            grab_ports = 0
            print ("Finished grabbing ports")

        #if this block has been triggered by a previous iteration, grab the ports on this line/vlan and sort them by tagging state
        if (grab_ports == 1) or (grab_ports == 2):
            #this is for vlans that only have one tagged state on their ports
            if (not line.startswith(" tagged")) and (not line.startswith(" untagged")):
                grab_ports = 0
                print ("Finished grabbing ports")
                continue
            #split the line by ethe to (sort of) get ports
            port_list_v1 = line.split(" ethe ")
            port_list_v2 = []
            for bogo_port in port_list_v1:
                #skip the beginning of the line
                if (bogo_port == " tagged") or (bogo_port == " untagged"):
                    continue
                else:
                    port_list_v2.append(bogo_port)
            #account for ranges of ports
            port_list_v3 = []
            for bogo_port in port_list_v2:
                if re.search("to", bogo_port):
                    print ("Found a range")
                    #get the prefix for the range
                    stack_module_list = re.findall("^(\d/\d/)", bogo_port)
                    #this is just hoop jumping because of datatypes
                    for thing in stack_module_list:
                        stack_module = thing
                    print ("Range prefix is " + stack_module)

                    #get the first and last ports
                    first_last_list = bogo_port.split(" to ")
                    first_last_list_v2 = []
                    for bogo_port in first_last_list:
                        output_port = re.sub("^\d+/\d+/", "", bogo_port)
                        first_last_list_v2.append(output_port)

                    first_port = first_last_list_v2[0]
                    last_port = first_last_list_v2[1]

                    print ("First port in range: " + first_port)
                    print ("Last port in range: " + last_port)
                    #iterate for every integer between and including the first and last port number
                    current_port = int(first_port)
                    #one more because we're including the last port in the range
                    target_port = int(last_port) + 1
                    while not current_port == target_port:
                        output_port = stack_module + str(current_port)
                        print ("Found port in range " + output_port)
                        port_list_v3.append(output_port)
                        current_port += 1
                else:
                    port_list_v3.append(bogo_port)
                    print ("Found individual port " + bogo_port)

            if line.startswith(" tagged"):
                vlan_ports[working_vlan_id]["tagged"] = []
                for port in port_list_v3:
                    vlan_ports[working_vlan_id]["tagged"].append(port)
                    print ("Port " + port + " is tagged")
            if line.startswith(" untagged"):
                vlan_ports[working_vlan_id]["untagged"] = []
                for port in port_list_v3:
                    vlan_ports[working_vlan_id]["untagged"].append(port)
                    print ("Port " + port + " is untagged")
            grab_ports += 1
            #print ("incremented the port grabber")

        #grab each vlan id, and trigger the port grab above on next iteration
        if re.search("^vlan \d+", line) and (grab_ports == 0):
            bogus_vlan_list = re.findall("^vlan (\d+)", line)
            for vlan in bogus_vlan_list:
                #toss them in the dictionary as keys with values set to an empty dictionary
                vlan_ports[vlan] = {}
                print ("Found VLAN " + vlan)
                working_vlan_id = vlan
            #trigger the previous block of code on next iteration
            grab_ports = 1
            print ("Triggered port grab...")

    return vlan_ports

def port_vlan_finder(target_port, vlan_ports):
    output_vlan_ids = []
    tagging_state = ""

    for vlan_id in vlan_ports:
        print ("Searching VLAN: " + vlan_id)

        try:
            for port in vlan_ports[vlan_id]["tagged"]:
                if target_port == port:
                    output_vlan_ids.append(vlan_id)
                    tagging_state = "tagged"
                    print ("Found port " + target_port + " tagged in vlan: " + vlan_id)
        except KeyError:
            print ("VLAN " + vlan_id + " has no tagged ports on this device. (Verify direction of slashes for port id!)")
        try:
            for port in vlan_ports[vlan_id]["untagged"]:
                if target_port == port:
                    output_vlan_ids.append(vlan_id)
                    tagging_state = "untagged"
                    print ("Found port " + target_port + " untagged in vlan: " + vlan_id)
        except KeyError:
            print ("VLAN " + vlan_id + " has no untagged ports on this device. (Verify direction of slashes for port id!)")

    if len(output_vlan_ids) == 0:
        print ("This port is unassigned.")

    return output_vlan_ids, tagging_state

def voip_vlan_finder(vlan_ports):
    done = 0

    for vlan_id in vlan_ports:
        if re.search("3\d\d\d", vlan_id):
            if done == 1:
                print ("Found more than one Voice VLAN. This program will exit.")
                quit()
            voice_vlan = vlan_id
            done += 1

    return voice_vlan


def single_target(chan, tacacs_pw, enable_pw):
    while True:
        #buff is returned after a successful run
        buff = ""

        #grab target data and touch-up
        target_switch = input("Target switch: ")
        if not target_switch.endswith(".local"):
            target_switch = target_switch + ".local"
        target_port = input("Target port (XX/XX/XX): ")
        if (not re.match("\d+/\d+/\d+", target_port)) or (len(target_port) > 7):
            print (target_port + " is not a well-formed port number. Please try again.")
            continue
        uc360 = input("Is this port for a UC360 conference phone? (y/N):")

        #test tacacs credentials
        try:
            #open connection to comm-vss-g because it's a good, reliable hostname that's a good test point
            ssh_brocade = paramiko.SSHClient()
            ssh_brocade.set_missing_host_key_policy(
                paramiko.AutoAddPolicy())
            ssh_brocade.connect(target_switch,
                password=tacacs_pw)
        except:
            print ("TACACS login failure! Try again.")
            continue

        #test enable
        channel = ssh_brocade.invoke_shell()
        channel.send("enable\r")
        while not channel.recv_ready():
            time.sleep(.1)
        resp = channel.recv(9999).decode("utf-8")
        buff += resp
        #the first is for brocade, the second is for cisco
        while not (resp.endswith("Password: ") or resp.endswith("Password:")):
            time.sleep(.1)
            resp = channel.recv(9999).decode("utf-8")
            buff += resp

        #send password
        channel.send(enable_pw + "\r")
        while not channel.recv_ready():
            time.sleep(.1)
        resp = channel.recv(9999).decode("utf-8")
        buff += resp
        if resp.endswith(">"):
            print ("Enable password failure! Try again.")
            continue
        while not resp.endswith("#"):
            time.sleep(.1)
            resp = channel.recv(9999).decode("utf-8")
            buff += resp

        print ("Login success!")
        break

    buff += disable_paging_brocade(channel)
    minibuff = send_command("show running-config", channel)
    buff += minibuff
    vlan_ports = vlan_ports_parser(minibuff)
    detected_vlan_ids, tagging_state = port_vlan_finder(target_port, vlan_ports)
    for vlan in detected_vlan_ids:
        if re.search("3\d\d\d", vlan):
            data_vlan = vlan
    voice_vlan = voip_vlan_finder(vlan_ports)

    #run some checks on the vlan tagging state of the port
    if (len(detected_vlan_ids) == 0) or ("1" in detected_vlan_ids):
        print (target_switch + " " + target_port + " is unassigned. Try again.")
        buff = ""
        return ""

    if (len(detected_vlan_ids) > 1) or (tagging_state == "tagged"):
        print (target_switch + " " + target_port + " is already in more than one vlan or is tagged for at least one. Try again.")
        buff = ""
        return ""

    for vlan_id in detected_vlan_ids:
        if re.search("3\d\d\d", vlan_id):
            print (target_switch + " " + target_port + " is already a member of a VoIP vlan. Try again.")
            buff = ""
            return ""
        if re.search("15\d\d", vlan_id):
            print (target_switch + " " + target_port + " is already a member of a management vlan. Try again.")
            buff = ""
            return ""
        if re.search("16\d\d", vlan_id):
            print (target_switch + " " + target_port + " is already a member of a WLAN management vlan. Try again.")
            buff = ""
            return ""
        if re.search("17\d\d", vlan_id):
            print (target_switch + " " + target_port + " is already a member of a BMS vlan. Try again.")
            buff = ""
            return ""

    #if the above tests succeed, then proceed to VoIP-ready the port

    print (target_switch + " " + target_port + " is a member of data VLAN " + detected_vlan_ids[0] + ", and will be added to VLAN " + voice_vlan + ".")

    if not yestoall == 1:
        cntinue = input("Continue? (y/N): ")
    else:
        cntinue = "y"
    if (not cntinue == "y") and (not cntinue == "yes"):
        print ("Try again.")
        buff = ""
        return ""

    minibuff = send_command("configure terminal", channel)
    buff += minibuff

    minibuff = send_command("vlan " + detected_vlan_ids[0], channel)
    buff += minibuff

    minibuff = send_command("no untagged eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("tagged eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("vlan " + voice_vlan, channel)
    buff += minibuff

    minibuff = send_command("tagged eth " + target_port, channel)
    buff += minibuff

    #send 5x because experience has shown that the settign doesn't always take the first time
    minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("lldp enable snmp notifications ports ethe " + target_port, channel)
    buff += minibuff

    minibuff = send_command("lldp enable snmp med-topo-change-notifications ports ethe " + target_port, channel)
    buff += minibuff

    minibuff = send_command("int ethe " + target_port, channel)
    buff += minibuff

    minibuff = send_command("dual-mode " + detected_vlan_ids[0], channel)
    buff += minibuff

    minibuff = send_command("voice-vlan " + voice_vlan, channel)
    buff += minibuff

    #uc360s take more power
    if (uc360 == "y") or (uc360 == "yes"):
        minibuff = send_command("inline power power-limit 30000", channel)
        buff += minibuff

    else:
        minibuff = send_command("inline power ", channel)
        buff += minibuff

    minibuff = send_command("write memory", channel)
    buff += minibuff

    print ("Done!")

    # print (vlan_ports)
    # print (detected_vlan_ids)
    # print (tagging_state)
    channel.close()
    return buff

def single_target_r(chan, tacacs_pw, enable_pw):
    while True:
        #buff is returned after a successful run
        buff = ""

        #grab target data and touch-up
        target_switch = input("Target switch: ")
        if not target_switch.endswith(".local"):
            target_switch = target_switch + ".local"
        target_port = input("Target port (XX/XX/XX): ")
        if (not re.match("\d+/\d+/\d+", target_port)) or (len(target_port) > 7):
            print (target_port + " is not a well-formed port number. Please try again.")
            continue

        #test tacacs credentials
        try:
            #open connection to comm-vss-g because it's a good, reliable hostname that's a good test point
            ssh_brocade = paramiko.SSHClient()
            ssh_brocade.set_missing_host_key_policy(
                paramiko.AutoAddPolicy())
            ssh_brocade.connect(target_switch,
                password=tacacs_pw)
        except:
            print ("TACACS login failure! Try again.")
            continue

        #test enable
        channel = ssh_brocade.invoke_shell()
        channel.send("enable\r")
        while not channel.recv_ready():
            time.sleep(.1)
        resp = channel.recv(9999).decode("utf-8")
        buff += resp
        #the first is for brocade, the second is for cisco
        while not (resp.endswith("Password: ") or resp.endswith("Password:")):
            time.sleep(.1)
            resp = channel.recv(9999).decode("utf-8")
            buff += resp

        #send password
        channel.send(enable_pw + "\r")
        while not channel.recv_ready():
            time.sleep(.1)
        resp = channel.recv(9999).decode("utf-8")
        buff += resp
        if resp.endswith(">"):
            print ("Enable password failure! Try again.")
            continue
        while not resp.endswith("#"):
            time.sleep(.1)
            resp = channel.recv(9999).decode("utf-8")
            buff += resp

        print ("Login success!")
        break

    buff += disable_paging_brocade(channel)
    minibuff = send_command("show running-config", channel)
    buff += minibuff
    vlan_ports = vlan_ports_parser(minibuff)
    detected_vlan_ids, tagging_state = port_vlan_finder(target_port, vlan_ports)
    #find data vlan and voice vlan
    for vlan in detected_vlan_ids:
        if not re.search("3\d\d\d", vlan):
            data_vlan = vlan
    voice_vlan = voip_vlan_finder(vlan_ports)

    #run some checks on the vlan tagging state of the port
    if (len(detected_vlan_ids) == 0) or ("1" in detected_vlan_ids):
        print (target_switch + " " + target_port + " is unassigned. Try again.")
        buff = ""
        return ""

    if (len(detected_vlan_ids) == 1) or (tagging_state == "untagged"):
        print (target_switch + " " + target_port + " is only on one vlan or is untagged. Try again.")
        buff = ""
        return ""

    counter = 0
    for vlan_id in detected_vlan_ids:
        if not re.search("3\d\d\d", vlan_id):
            counter += 1
    if not counter == 1:
        print (target_switch + " " + target_port + " is not a member of a VoIP vlan. Try again.")
        buff = ""
        return ""

    #if the above tests succeed, then proceed to un-VoIP the port

    print (target_switch + " " + target_port + " is a member of data VLAN " + data_vlan + " and will be removed from voice vlan " + voice_vlan + ".")

    if not yestoall == 1:
        cntinue = input("Continue? (y/N): ")
    else:
        cntinue = "y"
    if (not cntinue == "y") and (not cntinue == "yes"):
        print ("Try again.")
        buff = ""
        return ""

    minibuff = send_command("configure terminal", channel)
    buff += minibuff

    minibuff = send_command("int ethe " + target_port, channel)
    buff += minibuff

    minibuff = send_command("no dual-mode " + data_vlan, channel)
    buff += minibuff

    minibuff = send_command("no voice-vlan " + voice_vlan, channel)
    buff += minibuff

    minibuff = send_command("no inline power ", channel)
    buff += minibuff

    minibuff = send_command("vlan " + voice_vlan, channel)
    buff += minibuff

    minibuff = send_command("no tagged eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("vlan " + data_vlan, channel)
    buff += minibuff

    minibuff = send_command("no tagged eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("untagged eth " + target_port, channel)
    buff += minibuff

    #send 5x because experience has shown that the setting doesn't always take the first time
    minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
    buff += minibuff

    minibuff = send_command("no lldp enable snmp notifications ports ethe " + target_port, channel)
    buff += minibuff

    minibuff = send_command("no lldp enable snmp med-topo-change-notifications ports ethe " + target_port, channel)
    buff += minibuff

    minibuff = send_command("write memory", channel)
    buff += minibuff

    print ("Done!")

    # print (vlan_ports)
    # print (detected_vlan_ids)
    # print (tagging_state)
    channel.close()
    return buff

def list_target_r(chan, tacacs_pw, enable_pw, list_file):
    #buff is returned after a successful run
    buff = ""

    switch_port_power_dict = {}
    switch_list = []

    #prefill dictionary with switch_name lists with empty port list
    for line in list_file:
        line = line.strip()
        line = line.split(",")
        switch_name = line[0]
        if switch_name not in switch_list:
            switch_list.append(switch_name)
            switch_port_power_dict[switch_name] = []
        #rest of loop fills in ports
        port_id = line[1]
        #account for missing power flag fields that imply no flag
        try:
            power_flag = line[2]
        except:
            power_flag = ""
        port_power_list = [port_id, power_flag]
        switch_port_power_dict[switch_name].append(port_power_list)

    port_counter = 0
    for switch in switch_port_power_dict:
        print (switch, switch_port_power_dict[switch])
        for port_power in switch_port_power_dict[switch]:
            port_counter += 1

    print ("Found " + str(port_counter) + " ports to change.")

    if not yestoall == 1:
        confirm = input("Do you want to proceed? (N/y): ")
    else:
        confirm = "y"

    if confirm == "y" or confirm == "yes":

        skipped_counter = 0
        counter = 0
        #for every given switch
        for target_switch in switch_port_power_dict:
            #for every list of ports and their properties at a given switch
            for port_list in switch_port_power_dict[target_switch]:
                #set target port to correct
                target_port = port_list[0]
                increase_power = port_list[1]

                #send tacacs credentials
                try:
                    ssh_brocade = paramiko.SSHClient()
                    ssh_brocade.set_missing_host_key_policy(
                        paramiko.AutoAddPolicy())
                    ssh_brocade.connect(target_switch,
                        password=tacacs_pw)
                except:
                    print ("TACACS login failure! Try again.")
                    quit()

                #enter enable
                channel = ssh_brocade.invoke_shell()
                channel.send("enable\r")
                while not channel.recv_ready():
                    time.sleep(.1)
                resp = channel.recv(9999).decode("utf-8")
                buff += resp
                #the first is for brocade, the second is for cisco
                while not (resp.endswith("Password: ") or resp.endswith("Password:")):
                    time.sleep(.1)
                    resp = channel.recv(9999).decode("utf-8")
                    buff += resp

                #send password
                channel.send(enable_pw + "\r")
                while not channel.recv_ready():
                    time.sleep(.1)
                resp = channel.recv(9999).decode("utf-8")
                buff += resp
                if resp.endswith(">"):
                    print ("Enable password failure! Try again.")
                    quit()
                while not resp.endswith("#"):
                    time.sleep(.1)
                    resp = channel.recv(9999).decode("utf-8")
                    buff += resp

                print ("Login success!")

                buff += disable_paging_brocade(channel)
                minibuff = send_command("show running-config", channel)
                buff += minibuff
                vlan_ports = vlan_ports_parser(minibuff)
                detected_vlan_ids, tagging_state = port_vlan_finder(target_port, vlan_ports)
                for vlan in detected_vlan_ids:
                    if not re.search("3\d\d\d", vlan):
                        data_vlan = vlan
                voice_vlan = voip_vlan_finder(vlan_ports)

                #run some checks on the vlan tagging state of the port
                if (len(detected_vlan_ids) == 0) or ("1" in detected_vlan_ids):
                    print (target_switch + " " + target_port + " is unassigned. This line will be skipped. (Verify direction of slashes for port id!)")
                    skipped_counter += 1
                    channel.close()
                    continue

                if (len(detected_vlan_ids) == 1) or (tagging_state == "untagged"):
                    print (target_switch + " " + target_port + " is only on one vlan or is untagged. This line will be skipped.")
                    skipped_counter += 1
                    channel.close()
                    continue

                vlan_counter = 0
                for vlan_id in detected_vlan_ids:
                    if not re.search("3\d\d\d", vlan_id):
                        vlan_counter += 1
                if not vlan_counter == 1:
                    print (target_switch + " " + target_port + " is not a member of a VoIP vlan. This line will be skipped.")
                    skipped_counter += 1
                    channel.close()
                    continue

                #if the above tests succeed, then proceed to VoIP-ready the port

                print (target_switch + " " + target_port + " is a member of data VLAN " + detected_vlan_ids[0] + ", and will be removed from VLAN " + voice_vlan + ".")

                print ("Choosing N will skip to the next line.")
                if not yestoall == 1:
                    cntinue = input("Continue? (y/N): ")
                else:
                    cntinue = "y"
                if (not cntinue == "y") and (not cntinue == "yes"):
                    print ("Skipping.")
                    skipped_counter += 1
                    channel.close()
                    continue

                minibuff = send_command("configure terminal", channel)
                buff += minibuff

                minibuff = send_command("int ethe " + target_port, channel)
                buff += minibuff

                minibuff = send_command("no dual-mode " + data_vlan, channel)
                buff += minibuff

                minibuff = send_command("no voice-vlan " + voice_vlan, channel)
                buff += minibuff

                minibuff = send_command("no inline power ", channel)
                buff += minibuff

                minibuff = send_command("vlan " + voice_vlan, channel)
                buff += minibuff

                minibuff = send_command("no tagged eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("vlan " + data_vlan, channel)
                buff += minibuff

                minibuff = send_command("no tagged eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("untagged eth " + target_port, channel)
                buff += minibuff

                #send 5x because experience has shown that the setting doesn't always take the first time
                minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("no lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("no lldp enable snmp notifications ports ethe " + target_port, channel)
                buff += minibuff

                minibuff = send_command("no lldp enable snmp med-topo-change-notifications ports ethe " + target_port, channel)
                buff += minibuff

                minibuff = send_command("write memory", channel)
                buff += minibuff

                counter += 1
                print ("Done with " + target_switch + " " + target_port)
                print ("Skipped " + str(skipped_counter) + " ports.")
                print ("Completed " + str(counter) + " ports.")
                # print (vlan_ports)
                # print (detected_vlan_ids)
                # print (tagging_state)
                channel.close()
        return buff

    else:
        print ("Exiting.")
        buff = ""
        return ""

def list_target(chan, tacacs_pw, enable_pw, list_file):
    #buff is returned after a successful run
    buff = ""

    switch_port_power_dict = {}
    switch_list = []

    #prefill dictionary with switch_name lists with empty port list
    for line in list_file:
        line = line.strip()
        line = line.split(",")
        switch_name = line[0]
        if switch_name not in switch_list:
            switch_list.append(switch_name)
            switch_port_power_dict[switch_name] = []
        #rest of loop fills in ports
        port_id = line[1]
        #account for missing power flag fields that imply no flag
        try:
            power_flag = line[2]
        except:
            power_flag = ""
        port_power_list = [port_id, power_flag]
        switch_port_power_dict[switch_name].append(port_power_list)

    port_counter = 0
    for switch in switch_port_power_dict:
        print (switch, switch_port_power_dict[switch])
        for port_power in switch_port_power_dict[switch]:
            port_counter += 1

    print ("Found " + str(port_counter) + " ports to change.")

    if not yestoall == 1:
        confirm = input("Do you want to proceed? (N/y): ")
    else:
        confirm = "y"

    if confirm == "y" or confirm == "yes":

        skipped_counter = 0
        counter = 0
        #for every given switch
        for target_switch in switch_port_power_dict:
            #for every list of ports and their properties at a given switch
            for port_list in switch_port_power_dict[target_switch]:
                #set target port to correct
                target_port = port_list[0]
                increase_power = port_list[1]

                #send tacacs credentials
                try:
                    ssh_brocade = paramiko.SSHClient()
                    ssh_brocade.set_missing_host_key_policy(
                        paramiko.AutoAddPolicy())
                    ssh_brocade.connect(target_switch,
                        password=tacacs_pw)
                except:
                    print ("TACACS login failure! Try again.")
                    quit()

                #enter enable
                channel = ssh_brocade.invoke_shell()
                channel.send("enable\r")
                while not channel.recv_ready():
                    time.sleep(.1)
                resp = channel.recv(9999).decode("utf-8")
                buff += resp
                #the first is for brocade, the second is for cisco
                while not (resp.endswith("Password: ") or resp.endswith("Password:")):
                    time.sleep(.1)
                    resp = channel.recv(9999).decode("utf-8")
                    buff += resp

                #send password
                channel.send(enable_pw + "\r")
                while not channel.recv_ready():
                    time.sleep(.1)
                resp = channel.recv(9999).decode("utf-8")
                buff += resp
                if resp.endswith(">"):
                    print ("Enable password failure! Try again.")
                    quit()
                while not resp.endswith("#"):
                    time.sleep(.1)
                    resp = channel.recv(9999).decode("utf-8")
                    buff += resp

                print ("Login success!")

                buff += disable_paging_brocade(channel)
                minibuff = send_command("show running-config", channel)
                buff += minibuff
                vlan_ports = vlan_ports_parser(minibuff)
                detected_vlan_ids, tagging_state = port_vlan_finder(target_port, vlan_ports)
                voice_vlan = voip_vlan_finder(vlan_ports)

                #run some checks on the vlan tagging state of the port
                if (len(detected_vlan_ids) == 0) or ("1" in detected_vlan_ids):
                    print (target_switch + " " + target_port + " is unassigned. This line will be skipped. (Verify direction of slashes for port id!)")
                    skipped_counter += 1
                    channel.close()
                    continue

                if (len(detected_vlan_ids) > 1) or (tagging_state == "tagged"):
                    print (target_switch + " " + target_port + " is already in more than one vlan or is tagged for at least one. This line will be skipped.")
                    skipped_counter += 1
                    channel.close()
                    continue

                for vlan_id in detected_vlan_ids:
                    if re.search("3\d\d\d", vlan_id):
                        print (target_switch + " " + target_port + " is already a member of a VoIP vlan. This line will be skipped.")
                        skipped_counter += 1
                        channel.close()
                        continue
                    if re.search("15\d\d", vlan_id):
                        print (target_switch + " " + target_port + " is already a member of a management vlan. This line will be skipped.")
                        skipped_counter += 1
                        channel.close()
                        continue
                    if re.search("16\d\d", vlan_id):
                        print (target_switch + " " + target_port + " is already a member of a WLAN management vlan. This line will be skipped.")
                        skipped_counter += 1
                        channel.close()
                        continue
                    if re.search("17\d\d", vlan_id):
                        print (target_switch + " " + target_port + " is already a member of a BMS vlan. This line will be skipped.")
                        skipped_counter += 1
                        channel.close()
                        continue

                #if the above tests succeed, then proceed to VoIP-ready the port

                print (target_switch + " " + target_port + " is a member of data VLAN " + detected_vlan_ids[0] + ", and will be added to VLAN " + voice_vlan + ".")

                print ("Choosing N will skip to the next line.")
                if not yestoall == 1:
                    cntinue = input("Continue? (y/N): ")
                else:
                    cntinue = "y"
                if (not cntinue == "y") and (not cntinue == "yes"):
                    print ("Skipping.")
                    skipped_counter += 1
                    channel.close()
                    continue

                minibuff = send_command("configure terminal", channel)
                buff += minibuff

                minibuff = send_command("vlan " + detected_vlan_ids[0], channel)
                buff += minibuff

                minibuff = send_command("no untagged eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("tagged eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("vlan " + voice_vlan, channel)
                buff += minibuff

                minibuff = send_command("tagged eth " + target_port, channel)
                buff += minibuff

                #send 5x because experience has shown that the settign doesn't always take the first time
                minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("lldp med network-policy application voice tagged vlan " + voice_vlan + " priority 5 dscp 46 ports eth " + target_port, channel)
                buff += minibuff

                minibuff = send_command("lldp enable snmp notifications ports ethe " + target_port, channel)
                buff += minibuff

                minibuff = send_command("lldp enable snmp med-topo-change-notifications ports ethe " + target_port, channel)
                buff += minibuff

                minibuff = send_command("int ethe " + target_port, channel)
                buff += minibuff

                minibuff = send_command("dual-mode " + detected_vlan_ids[0], channel)
                buff += minibuff

                minibuff = send_command("voice-vlan " + voice_vlan, channel)
                buff += minibuff

                #increase_power is to flag UC360s
                if increase_power == "x":
                    minibuff = send_command("inline power power-limit 30000", channel)
                    buff += minibuff

                else:
                    minibuff = send_command("inline power ", channel)
                    buff += minibuff

                minibuff = send_command("write memory", channel)
                buff += minibuff

                counter += 1
                print ("Done with " + target_switch + " " + target_port)
                print ("Skipped " + str(skipped_counter) + " ports.")
                print ("Completed " + str(counter) + " ports.")
                # print (vlan_ports)
                # print (detected_vlan_ids)
                # print (tagging_state)
                channel.close()
        return buff

    else:
        print ("Exiting.")
        return buff

if __name__ == "__main__":
    switches = []
    counter = 0
    for switch in sys.argv:
        if counter == 0:
            counter += 1
            continue
        switches.append(switch)

    list_mode = 0
    revert = 0
    noverify = 0
    yestoall = 0
    for switch in switches:
        if (switch == "-?") or ((switch == "--help") or (switch == "-h")):
            print ("""
This program is used to quickly provision VoIP ports on Brocade switches in UCSC's network environment.

If run by itself ("python voiper.py"), the program will run in single-target mode. This mode will keep looping until the program is exited with CRTL-C or Command-C, in order to provision many individual ports without asking for credentials each time.

If supplied a CSV filename ("python voiper.py filename.csv"), the program will run in CSV mode. Here is an example of a CSV file that will work with this program:

    sw7175-05.local,1/1/10
    sw7175-04.local,2/1/12,x

The first two fields are for switch hostname and port, respectively. The third field will flag a port for excess PoE (for use with UC360 conference phones). This field is not important for de-provisioning (explained below), and in that mode the field is ignored. All terminal output from interacting with target switches is recorded in voiper_list.log when running in CSV mode.

If run with the -r switch, the program will revert the target port back to a standard data port in either CSV mode or single-targer mode.

If run with the --yestoall switch, the program will not confirm before making changes in list mode.

There are various checks built in to avoid unwanted changes. For instance, if more than one 3XXX (voice) vlan is detected on the switch it will complain and die. Any questions or suggestions can be directed to Nik Hildebrand in TelOps.
            """)
        elif switch == "-r":
            revert = 1
        elif switch == "--yestoall":
            yestoall = 1
        elif switch == "--noverify":
            noverify = 1
        else:
            list_filename = switch
            list_mode = 1

    if list_mode == 1:
        try:
            list_file = open(list_filename)
        except:
            print ("List filename incorrect or file does not exist. Try again.")
            quit()

    #loop to run for individual ports
    if list_mode == 0 and revert == 0:
        print ("Running in single-target mode.")
        buff = ""
        tacacs_pw, enable_pw, channel = test_credentials()
        while True:
            buff += single_target(channel, tacacs_pw, enable_pw)
            print (buff)

    #list mode
    if list_mode == 1 and revert == 0:
        print ("Running in CSV mode for " + list_filename)
        buff = ""
        tacacs_pw, enable_pw, channel = test_credentials()
        buff += list_target(channel, tacacs_pw, enable_pw, list_file)
        log = open("voiper_list.log", "w+")
        for line in buff:
            log.write(line)
        log.close()
        print ("See voiper_list.log for details of this operation.")

    #revert individual
    if list_mode == 0 and revert == 1:
        print ("Running in single-target revert mode.")
        buff = ""
        tacacs_pw, enable_pw, channel = test_credentials()
        while True:
            buff += single_target_r(channel, tacacs_pw, enable_pw)
            print (buff)

    #revert list
    if list_mode == 1 and revert == 1:
        print ("Running in CSV revert mode for " + list_filename)
        buff = ""
        tacacs_pw, enable_pw, channel = test_credentials()
        buff += list_target_r(channel, tacacs_pw, enable_pw, list_file)
        log = open("voiper_list.log", "w+")
        for line in buff:
            log.write(line)
        log.close()
        print ("See voiper_list.log for details of this operation.")
