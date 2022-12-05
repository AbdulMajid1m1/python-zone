import socket
import json
import random
import argparse
import socketserver
import threading
from urllib.parse import urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer
import re
import json
import threading

# utility function to get the local LAN IP address
def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        s.connect(('10.254.254.254', 1)) # just a dummy IP address - can be anything, really
        IP = s.getsockname()[0] # this is where the magic happens
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

udpport = 57888
myip = get_ip()
httpport = 7888 # http port (can be any valid port really - I just had to pick something)
# Default = randomize num zones, faves, hasac and http port
nzones = random.randint(2,8) # nzones = 2..8
nfaves = random.randint(0,4) # nfaves = 0..4
hasac = random.choice([0, 1]) # hasac = on/off (random)

# But you can also specify
parser = argparse.ArgumentParser(description = 'Get supplied arguments') # can also specify on command line
parser.add_argument('-z', '--zones', dest='nzones', type=int, help='Number of zones (default: random 2-8)')
parser.add_argument('-f', '--favs', '--faves' , dest='nfaves', type=int, help='Number of faves (default: random 0-4)')
parser.add_argument('-a', '--ac', '--hasac', dest='hasac', type=int, help='Has AC relay (default: random)')
parser.add_argument('-p', '--port' , dest='httpport', type=int, help='HTTP port (default: 7888)')
args = parser.parse_args()
#print(args)

# Load specific values 
if args.nzones is not None and args.nzones >= 2 and args.nzones <= 8: # save specified nzones (if any)
    nzones = args.nzones

if args.nfaves is not None and args.nfaves >= 0 and args.nfaves <= 4: # same for nfaves
    nfaves = args.nfaves

if args.hasac is not None and args.hasac >=0 and args.hasac <= 1: # and hasac
    hasac = args.hasac

if args.httpport is not None and args.httpport > 0 and args.httpport <= 65535: # and httpport
    httpport = args.httpport

# Select random zone names
zonenames = random.sample(["Kitchen ", "Lounge  ", "Garage  ", "Bedrm 1 ", "Bedrm 2 ", "Bedrm 3 ", "Bedrm 4", "Dining  ", "Main Bed", "Hallway ", "WWWWWWWW", "AAAAAAAA"], nzones)

# Select random fave names and ids
favenames = random.sample(["Bedrooms", "Living ", "Outside ", "E. Wing ", "N. Wing ", "W. Wing ", "S. Wing "], nfaves)
faveids = random.sample([9,10,11,12], nfaves) # always a sampling of 9,10,11,12
faveids.sort() # but in order

# Initial "loading" myzone
myzone_loading = { "device":"myzone","protocol_version":1,"projcode":"B22A","projver":"221024.1800","mpm":"N3A-010.065",
    "loaded":0, "write_result":"ok" }
# Initial "loaded" myzone
myzone_loaded = { "device":"myzone","protocol_version":1,"projcode":"B22A","projver":"221024.1800","mpm":"N3A-010.065",
    "loaded":100,"relay_present":1,"relay_state":0,"zones_active":1,"nzones":8,"zone_info":[],"fave_info":[],"nfaves":4,"write_result":"ok" }

# Fill global stuff
myzone_loaded["relay_present"] = hasac
myzone_loaded["relay_state"] = random.choice([0,1])
myzone_loaded["zones_active"] = random.choice([0,1])

# Fill zones with stuff (random sw, pos)
myzone_loaded["nzones"] = nzones
zoneid=0
for zonename in zonenames:
    zoneid = zoneid + 1
    myzone_loaded["zone_info"].append({"id":zoneid, "name":zonename, "sw":random.choice([0,1]), "pos":5 * random.randint(1,20)})

# Fill faves with stuff (random sw)
myzone_loaded["nfaves"] = nfaves
for favenum in range(nfaves):
    myzone_loaded["fave_info"].append({"id":faveids[favenum], "name":favenames[favenum], "sw":random.choice([0,1])})

# Show initial json data that will (Eventually) be sent
print(json.dumps(myzone_loaded))

# Subclass the DatagramRequestHandler
class MyUDPRequestHandler(socketserver.DatagramRequestHandler):
    # Override the handle() method
    def handle(self):
        # Receive and print the datagram received from client
        print("Recieved one request from {}".format(self.client_address[0]))
        json_request = json.loads(self.rfile.read())

        if (json_request["device"] == "myzone" and json_request["msg"] == "search"):
            print("Replying to search with ip={ip} httpport={port}".format( ip = myip, port = httpport))
            obj_reply = { "device": "myzone", "msg": "found", "ip": myip, "httpport": httpport, "pollurl": "http://{ip}:{port}/point".format( ip = myip, port = httpport)}
            self.wfile.write(json.dumps(obj_reply).encode())
            self.wfile.write("\r\n".encode())

class HTTPRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if re.search('/point*', self.path):
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            if (myzone_loading["loaded"] < 100): # still loading
                data = json.dumps(myzone_loading) # show user
                myzone_loading["loaded"] = myzone_loading["loaded"] + 17 # pretend to keep loading
            else: # fully loaded, so now we can parse args
                getparams = parse_qs(urlparse(self.path).query)

                # load all params: should be numeric
                id = getparams.get("id")
                if id is not None:
                    id = int(id[0])
                        
                sw = getparams.get("sw")
                if id is not None and sw is not None:
                    sw = int(sw[0])
                
                pos = getparams.get("pos")
                if pos is not None:
                    pos = int(pos[0])

                relay_state = getparams.get("relay_state")
                if relay_state is not None:
                    relay_state = int(relay_state[0])

                zones_active = getparams.get("zones_active")
                if zones_active is not None:
                    zones_active = int(zones_active[0])

                # now, do sanity check
                write_result = "ok"
                if id is not None and id >= 1 and id <= nzones: # it's a valid zone id
                    write_result = "fail" # assume fail
                    if sw is not None and sw >= 0 and sw <= 1: # good sw?
                        myzone_loaded["zone_info"][id-1]["sw"] = sw # write it
                        write_result = "ok"

                    if pos is not None and pos >= 5 and pos <= 100 and (pos % 5) == 0: # good pos?
                        myzone_loaded["zone_info"][id-1]["pos"] = pos # write it
                        write_result = "ok"

                elif id is not None and id in faveids: # it's a valid fave id
                    write_result = "fail"
                    if sw is not None and sw >= 0 and sw <= 1: # good sw?
                        for favenum in range(nfaves): # find matching fave
                            if myzone_loaded["fave_info"][favenum]["id"] == id:
                                myzone_loaded["fave_info"][favenum]["sw"] = sw # write switch
                                write_result = "ok"

                elif zones_active is not None: # altering zones_active
                    write_result = "fail"
                    if zones_active >= 0 and zones_active <= 1:
                        myzone_loaded["zones_active"] = zones_active # write it
                        write_result = "ok"

                elif relay_state is not None: # altering relay state
                    write_result = "fail"
                    if relay_state >= 0 and relay_state <= 1:
                        myzone_loaded["relay_state"] = relay_state
                        write_result = "ok"
                myzone_loaded["write_result"] = write_result

                # all writing done, so point to updated myzone_loaded
                data = json.dumps(myzone_loaded)

            self.wfile.write(data.encode('utf-8')) # the data to send (either loading or loaded)

        else:
            self.send_response(403)

        self.end_headers()

# Create a Server Instance
UDPServerObject = socketserver.ThreadingUDPServer(("",udpport), MyUDPRequestHandler)
httpserver = HTTPServer(("", httpport), HTTPRequestHandler)

print("listening for HTTP on port:", httpport)

t1 = threading.Thread(target=UDPServerObject.serve_forever)
t2 = threading.Thread(target=httpserver.serve_forever)
for t in t1, t2: t.start()
for t in t1, t2: t.join()
