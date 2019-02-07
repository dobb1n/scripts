#python 2.7 version of script for timing multiple get requests

import socket
import string
import sys
import threading
import time

# Parse inputs
host = "sit02-dlp-online-b.digital.lloydsbank.co.uk"
ip = ""
port = 443
num_requests = 5

#num_requests = int(sys.argv[1])

ip = socket.gethostbyname(host)

# Create a shared variable for thread counts
thread_num = 0
thread_num_mutex = threading.Lock()


# Perform the request
def attack():
    
    
    # Create a raw socket
    dos = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    try:
        # Open the connection on that raw socket
        dos.connect((ip, port))

        # Send the request according to HTTP spec
        start = time.time()
        dos.send("GET /%s HTTP/1.1\nHost: %s\n\n")
        end = time.time()
        print end - start
    except socket.error, e:
        print "\n [ No connection, server may be down ]: " + str(e)
    finally:
        # Close our socket gracefully
        dos.shutdown(socket.SHUT_RDWR)
        dos.close()


print "[#] Attack started on " + host + " (" + ip + ") || Port: " + str(port) + " || # Requests: " + str(num_requests)

# Spawn a thread per request
all_threads = []
for i in xrange(num_requests):
    t1 = threading.Thread(target=attack)
    t1.start()
    all_threads.append(t1)

    # Adjusting this sleep time will affect requests per second
    time.sleep(0.01)

for current_thread in all_threads:
    current_thread.join()  # Make the main thread wait for the children threads