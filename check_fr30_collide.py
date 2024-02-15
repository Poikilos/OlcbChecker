#!/usr/bin/env python3.10
'''
This uses a CAN link layer to check response to an CID frame alias collision

Usage:
python3.10 check_fr20_ame.py

The -h option will display a full list of options.
'''

import sys

from openlcb.nodeid import NodeID
from openlcb.canbus.canframe import CanFrame
from openlcb.canbus.controlframe import ControlFrame
from queue import Empty

import olcbchecker.framelayer

def getFrame(timeout=0.3) :
    return olcbchecker.framelayer.readQueue.get(True, timeout)

def purgeFrames(timeout=0.3):
    while True :
        try :
            received = getFrame(timeout) # timeout if no entries
        except Empty:
             break

def check():
    # set up the infrastructure

    trace = olcbchecker.framelayer.trace # just to be shorter
    timeout = 0.3
    
    purgeFrames()

    ###############################
    # checking sequence starts here
    ###############################

    # send the AME frame to start the exchange
    ame = CanFrame(ControlFrame.AME.value, 0x001)  # bogus alias
    olcbchecker.framelayer.sendCanFrame(ame)
    
    try :
        # check for AMD frame from expected node (might be more than one AMD frame)
        while True: 
            waitFor = "waiting for AMD frame in first part"
            reply1 = getFrame()
            if (reply1.header & 0xFF_FFF_000) != 0x10_701_000 :
                print ("Failure - frame was not AMD frame in first part")
                return 3
        
            # check it carries a node ID
            if len(reply1.data) < 6 :
                print ("Failure - first AMD frame did not carry node ID")
                return 3
        
            # and it's the right node ID
            targetnodeid = olcbchecker.framelayer.configure.targetnodeid
            if targetnodeid == None :
                # take first one we get 
                targetnodeid = str(NodeID(reply1.data))
                originalAlias = reply1.header&0xFFF
                break  
            if NodeID(targetnodeid) != NodeID(reply1.data) :
                # but this wasn't the right one, get another
                continue
                
            # got the right one, so now have it's orignal alias
            originalAlias = reply1.header&0xFFF
            break
 
        purgeFrames()
        
        # Send a CID using that alias
        cid = CanFrame(ControlFrame.CID.value, originalAlias, [])
        olcbchecker.framelayer.sendCanFrame(cid)

        # check for RID frame
        waitFor = "waiting for RID in response to CID frame"
        reply = getFrame()
        if (reply.header & 0xFF_FFF_000) != 0x10_700_000 :
            print ("Failure - frame was not RID frame in second part")
            return 3

        # collision in CID properly responded to, lets try an AMD alias collision
        amd = CanFrame(ControlFrame.AMD.value, originalAlias, NodeID(targetnodeid).toArray())
        olcbchecker.framelayer.sendCanFrame(amd)

        # check for AMR frame
        waitFor = "waiting for AMR in response to AMD frame"
        reply = getFrame()
        if (reply.header & 0xFF_FFF_000) != 0x10_703_000 :
            print ("Failure - frame was not AMR frame in second part")
            return 3
        
        # check for _optional_ CID 7 frame with different alias
        newAlias = 0  # zero indicates invalid, not allocated
        try :
            replyCIDp = getFrame()
            if (replyCIDp.header & 0xFF_000_000) != 0x17_000_000 :
                print ("Failure - frame was not CID frame in second part")
                return 3
            # check for _different_ alias
            if (replyCIDp.header & 0x00_000_FFF) == originalAlias :
                print ("Failure - did not receive different alias on CID in second part")
                return 3
            # OK, remember this alias
            newAlias = replyCIDp.header & 0x00_000_FFF

        except Empty : 
            # this is an OK case too
            pass
        
         # loop for pause or AMD
        amdReceived = False
        try :
            # check for AMD frame from expected node (might be more AMD frames from others)
            while True: 
                waitFor = "waiting for AMD frame in second part"
                reply2 = getFrame()
                if (reply2.header & 0xFF_FFF_000) != 0x10_701_000 :
                    # wasn't AMD
                    continue
        
                # check it carries a node ID
                if len(reply2.data) < 6 :
                    print ("Failure - additional AMD frame did not carry node ID")
                    return 3
        
                # and it's the right node ID
                if not NodeID(targetnodeid) == NodeID(reply2.data) :
                    # but this wasn't the right one, get another
                    continue
                
                # and it's the right alias
                # this means different from prior alias
                # and, if another was allocated via CID above, matches that
                thisAlias = reply2.header & 0x00_000_FFF
                if thisAlias == originalAlias :
                    print("Failure - found original alias in second AMD")
                    return 3
                if newAlias != 0 and (newAlias != thisAlias) :
                    print("Failure - AMD alias did not match newly allocated one")
                    return 3

                # got the right one, so now have seen an AMD
                amdReceived = True
                break
        except Empty : 
            # this is an OK case too - no AMD received
            pass
        
        # wait for traffic to subside
        purgeFrames()

        # finally, send an AME and check results against above
        ame = CanFrame(ControlFrame.AME.value, 0x001)  # bogus alias
        olcbchecker.framelayer.sendCanFrame(ame)
        
        countAMDs = 0
        try :
            # check for AMD frame from expected node (might be more AMD frames from others)
            while True: 
                reply3 = getFrame()
                if (reply3.header & 0xFF_FFF_000) != 0x10_701_000 :
                    # wasn't AMD, skip
                    continue
        
                # check it carries a node ID - is this really an error?
                if len(reply3.data) < 6 :
                    continue
        
                # and it's the right node ID
                if NodeID(targetnodeid) != NodeID(reply3.data) :
                    # but this wasn't the right one, get another
                    continue
        
                # remember that we got one
                countAMDs += 1
                
                
        except Empty : 
            # have run out of replies to that AME
            # check for right number of AMD replies
            
            if amdReceived and countAMDs != 1 :
                print ("Failure - expected 1 AMD in third part and received "+str(countAMDs))
                return 3
            elif not amdReceived and countAMDs != 0 :
                print ("Failure - expected 0 AMDs in third part and received "+str(countAMDs))
                return 3
        
    except Empty:
        print ("Failure - did not receive expected frame while "+waitFor)
        return 3

    if trace >= 10 : print("Passed")
    return 0
 
if __name__ == "__main__":
    sys.exit(check())
    
