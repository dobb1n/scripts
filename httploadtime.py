#python 2.7 version


#script to http get a given resource
import urllib2
import time
import socket 
import ssl

# Variables of which site to request and how many times 
host = ""
numrequests = 5

# Convert site name into ip to avoid DNS lookups 
host = host.split("/")
ip = socket.gethostbyname(host[2])
strhost = host[0] + "//" + ip
strOut = []

#work around cert errors
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Function def for sending the GET request
def GETRequest(num):
    start = time.time()
    respcode = urllib2.urlopen(strhost, context=ctx)
    end = time.time()
    print ("request:", num, ",", respcode.getcode(), ",", end - start)
    return


# loop through number
for i in range(numrequests):
    GETRequest(i)
