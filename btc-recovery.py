#!/usr/bin/env python


from __future__ import print_function

import sys

# Error handling
def show_exception_and_exit(exc_type, exc_value, tb):
    import traceback
    traceback.print_exception(exc_type, exc_value, tb)
    raw_input("Press key to exit.")
    sys.exit(-1)
sys.excepthook = show_exception_and_exit

if sys.version_info.major == 3:
   from bsddb3.db import *
else:
   from bsddb.db import *

import os, sys, time
import json
import logging
import struct
import traceback
import socket
import types
import string

if sys.version_info.major != 3 :
    import exceptions

import hashlib
import random
import math

if sys.version_info.major != 3:
    import tkFileDialog
else:
    from tkinter import filedialog as tkFileDialog

import webbrowser
import fnmatch
import uuid

if sys.version_info.major == 3:
    import urllib.request as urllib2
else:
    import urllib2

import base64
import binascii

try:
    import Tkinter as tk
except ImportError:
    import tkinter as tk

max_version = 60000
addrtype = 0
json_db = {}
private_keys = []

def hash_160(public_key):
    md = hashlib.new('ripemd160')
    if sys.version_info.major == 3:
        md.update(hashlib.sha256(public_key.encode("cp437")).digest())
        return md.digest().decode("cp437")
    else:
        md.update(hashlib.sha256(public_key).digest())
        return md.digest()

def public_key_to_bc_address(public_key):
    h160 = hash_160(public_key)
    return hash_160_to_bc_address(h160)

def hash_160_to_bc_address(h160):
    vh160 = chr(addrtype) + h160
    h = Hash(vh160)
    addr = vh160 + h[0:4]
    return b58encode(addr)

def bc_address_to_hash_160(addr):
    bytes = b58decode(addr, 25)
    return bytes[1:21]

__b58chars = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
__b58base = len(__b58chars)

def b58encode(v):
    """ encode v, which is a string of bytes, to base58.        
    """

    if sys.version_info.major != 3 :
        long_value = long(0)
    else:
        long_value = 0

    for (i, c) in enumerate(v[::-1]):
        if sys.version_info.major == 3:
            long_value += (256**i) * c.encode("cp437")[0]
        else:
            long_value += (256**i) * ord(c)

    result = ''
    while long_value >= __b58base:
        div, mod = divmod(long_value, __b58base)
        result = __b58chars[mod] + result
        long_value = div
    result = __b58chars[long_value] + result

    # Bitcoin does a little leading-zero-compression:
    # leading 0-bytes in the input become leading-1s
    nPad = 0
    for c in v:
        if c == '\0': nPad += 1
        else: break

    return (__b58chars[0]*nPad) + result

def b58decode(v, length):
    """ decode v into a string of len bytes
    """
    if sys.version_info.major != 3 :
        long_value = long(0)
    else:
        long_value = 0

    for (i, c) in enumerate(v[::-1]):
        long_value += __b58chars.find(c) * (__b58base**i)

    result = ''
    while long_value >= 256:
        div, mod = divmod(long_value, 256)
        result = chr(mod) + result
        long_value = div
    result = chr(long_value) + result

    nPad = 0
    for c in v:
        if c == __b58chars[0]: nPad += 1
        else: break

    result = chr(0)*nPad + result
    if length is not None and len(result) != length:
        return None

    return result

# end of bitcointools base58 implementation


# address handling code

def Hash(data):
    if sys.version_info.major == 3:
        return hashlib.sha256(hashlib.sha256(data.encode("cp437")).digest()).digest().decode("cp437")
    else:
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def EncodeBase58Check(secret):
    hash = Hash(secret)
    return b58encode(secret + hash[0:4])

def PrivKeyToSecret(privkey):
    if len(privkey) == 279:
        return privkey[9:9+32]
    else:
        return privkey[8:8+32]

def SecretToASecret(secret, compressed=False):
    vchIn = chr((addrtype+128)&255) + secret
    if compressed: vchIn += '\01'
    return EncodeBase58Check(vchIn)

# bitcointools wallet.dat handling code

def create_env(db_dir):
    db_env = DBEnv(0)
    r = db_env.open(os.path.dirname(db_dir), (DB_CREATE|DB_INIT_LOCK|DB_INIT_LOG|DB_INIT_MPOOL|DB_INIT_TXN|DB_THREAD|DB_RECOVER))
    return db_env

def parse_CAddress(vds):
    d = {'ip':'0.0.0.0','port':0,'nTime': 0}
    try:
        d['nVersion'] = vds.read_int32()
        d['nTime'] = vds.read_uint32()
        d['nServices'] = vds.read_uint64()
        d['pchReserved'] = vds.read_bytes(12)
        d['ip'] = socket.inet_ntoa(vds.read_bytes(4))
        d['port'] = vds.read_uint16()
    except:
        pass
    return d

def deserialize_CAddress(d):
    return d['ip']+":"+str(d['port'])

def parse_setting(setting, vds):
    if setting[0] == "f":    # flag (boolean) settings
        return str(vds.read_boolean())
    elif setting[0:4] == "addr": # CAddress
        d = parse_CAddress(vds)
        return deserialize_CAddress(d)
    elif setting == "nTransactionFee":
        return vds.read_int64()
    elif setting == "nLimitProcessors":
        return vds.read_int32()
    return 'unknown setting'

class SerializationError(Exception):
    """ Thrown when there's a problem deserializing or serializing """

class BCDataStream(object):
    def __init__(self):
        self.input = None
        self.read_cursor = 0

    def clear(self):
        self.input = None
        self.read_cursor = 0

    def write(self, bytes):    # Initialize with string of bytes
        if self.input is None:
            self.input = bytes
        else:
            self.input += bytes

    def map_file(self, file, start):    # Initialize with bytes from file
        self.input = mmap.mmap(file.fileno(), 0, access=mmap.ACCESS_READ)
        self.read_cursor = start
    def seek_file(self, position):
        self.read_cursor = position
    def close_file(self):
        self.input.close()

    def read_string(self):
        # Strings are encoded depending on length:
        # 0 to 252 :    1-byte-length followed by bytes (if any)
        # 253 to 65,535 : byte'253' 2-byte-length followed by bytes
        # 65,536 to 4,294,967,295 : byte '254' 4-byte-length followed by bytes
        # ... and the Bitcoin client is coded to understand:
        # greater than 4,294,967,295 : byte '255' 8-byte-length followed by bytes of string
        # ... but I don't think it actually handles any strings that big.
        if self.input is None:
            raise SerializationError("call write(bytes) before trying to deserialize")

        try:
            length = self.read_compact_size()
        except IndexError:
            raise SerializationError("attempt to read past end of buffer")

        return self.read_bytes(length)

    def write_string(self, string):
        # Length-encoded as with read-string
        self.write_compact_size(len(string))
        self.write(string)

    def read_bytes(self, length):
        try:
            result = self.input[self.read_cursor:self.read_cursor+length]
            self.read_cursor += length
            if sys.version_info.major == 3:
                return result.decode("cp437")
            else:
                return result
        except IndexError:
            raise SerializationError("attempt to read past end of buffer")

        return ''

    def read_boolean(self): 
        if sys.version_info.major == 3:
            return self.read_bytes(1)[0] != bytes([x])
        else:
            return self.read_bytes(1)[0] != chr(0)
    def read_int16(self): return self._read_num('<h')
    def read_uint16(self): return self._read_num('<H')
    def read_int32(self): return self._read_num('<i')
    def read_uint32(self): return self._read_num('<I')
    def read_int64(self): return self._read_num('<q')
    def read_uint64(self): return self._read_num('<Q')

    def write_boolean(self, val): return self.write(chr(1) if val else chr(0))
    def write_int16(self, val): return self._write_num('<h', val)
    def write_uint16(self, val): return self._write_num('<H', val)
    def write_int32(self, val): return self._write_num('<i', val)
    def write_uint32(self, val): return self._write_num('<I', val)
    def write_int64(self, val): return self._write_num('<q', val)
    def write_uint64(self, val): return self._write_num('<Q', val)

    def read_compact_size(self):
        if sys.version_info.major == 3:
            size = self.input[self.read_cursor]
        else:
            size = ord(self.input[self.read_cursor])
        self.read_cursor += 1
        if size == 253:
            size = self._read_num('<H')
        elif size == 254:
            size = self._read_num('<I')
        elif size == 255:
            size = self._read_num('<Q')
        return size

    def write_compact_size(self, size):
        if size < 0:
            raise SerializationError("attempt to write size < 0")
        elif size < 253:
             self.write(chr(size))
        elif size < 2**16:
            self.write('\xfd')
            self._write_num('<H', size)
        elif size < 2**32:
            self.write('\xfe')
            self._write_num('<I', size)
        elif size < 2**64:
            self.write('\xff')
            self._write_num('<Q', size)

    def _read_num(self, format):
        (i,) = struct.unpack_from(format, self.input, self.read_cursor)
        self.read_cursor += struct.calcsize(format)
        return i

    def _write_num(self, format, num):
        s = struct.pack(format, num)
        self.write(s)

def open_wallet(db_env, wallet, writable=False):
    db = DB(db_env)
    flags = DB_THREAD | (DB_CREATE if writable else DB_RDONLY)
    try:
        r = db.open(os.path.basename(wallet), "main", DB_BTREE, flags)
    except DBError:
        r = True
    
    if r is not None:
        logging.error("Couldn't open wallet.dat/main. Try quitting Bitcoin and running this again.")
        sys.exit(1)
    
    return db

def parse_wallet(db, item_callback):
    kds = BCDataStream()
    vds = BCDataStream()

    for (key, value) in db.items():
        d = { }

        kds.clear(); kds.write(key)
        vds.clear(); vds.write(value)

        type = kds.read_string()

        d["__key__"] = key
        d["__value__"] = value
        d["__type__"] = type

        try:
            if type == "tx":
                d["tx_id"] = kds.read_bytes(32)
            elif type == "name":
                d['hash'] = kds.read_string()
                d['name'] = vds.read_string()
            elif type == "version":
                d['version'] = vds.read_uint32()
            elif type == "minversion":
                d['minversion'] = vds.read_uint32()
            elif type == "setting":
                d['setting'] = kds.read_string()
                d['value'] = parse_setting(d['setting'], vds)
            elif type == "key":
                d['public_key'] = kds.read_bytes(kds.read_compact_size())
                d['private_key'] = vds.read_bytes(vds.read_compact_size())
            elif type == "wkey":
                d['public_key'] = kds.read_bytes(kds.read_compact_size())
                d['private_key'] = vds.read_bytes(vds.read_compact_size())
                d['created'] = vds.read_int64()
                d['expires'] = vds.read_int64()
                d['comment'] = vds.read_string()
            elif type == "ckey":
                d['public_key'] = kds.read_bytes(kds.read_compact_size())
                d['crypted_key'] = vds.read_bytes(vds.read_compact_size())
            elif type == "mkey":
                d['nID'] = kds.read_int32()
                d['crypted_key'] = vds.read_bytes(vds.read_compact_size())
                d['salt'] = vds.read_bytes(vds.read_compact_size())
                d['nDerivationMethod'] = vds.read_int32()
                d['nDerivationIterations'] = vds.read_int32()
                d['vchOtherDerivationParameters'] = vds.read_bytes(vds.read_compact_size())
            elif type == "acc":
                d['account'] = kds.read_string()
                d['nVersion'] = vds.read_int32()
                d['public_key'] = vds.read_bytes(vds.read_compact_size())
            elif type == "acentry":
                d['account'] = kds.read_string()
                d['n'] = kds.read_uint64()
                d['nVersion'] = vds.read_int32()
                d['nCreditDebit'] = vds.read_int64()
                d['nTime'] = vds.read_int64()
                d['otherAccount'] = vds.read_string()
                d['comment'] = vds.read_string()
            
            item_callback(type, d)

        except Exception as e:
            traceback.print_exc()
            print("ERROR parsing wallet.dat, type %s" % type)
            print("key data in hex: %s"%key.encode('hex_codec'))
            print("value data in hex: %s"%value.encode('hex_codec'))
            sys.exit(1)

# end of bitcointools wallet.dat handling code

# wallet.dat reader / writer

def read_wallet(json_db, db_env, wallet, print_wallet, print_wallet_transactions, transaction_filter):
    db = open_wallet(db_env, wallet)

    json_db['keys'] = []
    json_db['names'] = {}

    def item_callback(type, d):
        global addrtype

        if type == "name":
            # dogecoin
            if d['hash'][0] == "D":
                addrtype = 30;
            # catcoin
            if d['hash'][0] == "9":
                addrtype = 21;
            # darkcoin
            if d['hash'][0] == "X":
                addrtype = 76;
            # litecoin
            if d['hash'][0] == "L":
                addrtype = 48;
            # novacoin
            if d['hash'][0] == "4":
                addrtype = 8;
            # ppcoin
            if d['hash'][0] == "P":
                addrtype = 55
            # primecoin
            if d['hash'][0] == "A":
                addrtype = 23;

            json_db['names'][d['hash']] = d['name']

        elif type == "version":
            json_db['version'] = d['version']

        elif type == "minversion":
            json_db['minversion'] = d['minversion']

        elif type == "key":
            addr = public_key_to_bc_address(d['public_key'])
            compressed = d['public_key'][0] != '\04'
            sec = SecretToASecret(PrivKeyToSecret(d['private_key']), compressed)
            private_keys.append(sec)
            json_db['keys'].append({'addr' : addr, 'sec' : sec})

        elif type == "wkey":
            if not json_db.has_key('wkey'): json_db['wkey'] = []
            json_db['wkey']['created'] = d['created']

        elif type == "ckey":
            addr = public_key_to_bc_address(d['public_key'])
            if sys.version_info.major == 3:
                ckey = binascii.hexlify(d['crypted_key'].encode("cp437")).decode(("cp437"))
                pubkey = binascii.hexlify(d['public_key'].encode("cp437")).decode(("cp437"))
            else:
                ckey = d['crypted_key'].encode("hex")
                pubkey = d['public_key'].encode("hex")
            json_db['keys'].append( {'addr' : addr, 'ckey': ckey, 'pubkey': pubkey })

        elif type == "mkey":
            mkey = {}
            mkey['nID'] = d['nID']
            if sys.version_info.major == 3:
                mkey['crypted_key'] = binascii.hexlify(d['crypted_key'].encode("cp437")).decode(("cp437"))
                mkey['salt'] = binascii.hexlify(d['salt'].encode("cp437")).decode(("cp437"))
                mkey['vchOtherDerivationParameters'] = binascii.hexlify(d['vchOtherDerivationParameters'].encode("cp437")).decode(("cp437"))
            else:
                mkey['crypted_key'] = d['crypted_key'].encode('hex')
                mkey['salt'] = d['salt'].encode('hex')
                mkey['vchOtherDerivationParameters'] = d['vchOtherDerivationParameters'].encode('hex')
            
            if 'nDerivationIterations' in d:
                mkey['nDeriveIterations'] = d['nDerivationIterations']
            else:
                mkey['nDeriveIterations'] = d['nDeriveIterations']
            mkey['nDerivationMethod'] = d['nDerivationMethod']
            json_db['mkey'] = mkey

        elif type == "acc":
            json_db['acc'] = d['account']
            print("Account %s (current key: %s)"%(d['account'], public_key_to_bc_address(d['public_key'])))

        elif type == "acentry":
            json_db['acentry'] = (d['account'], d['nCreditDebit'], d['otherAccount'], time.ctime(d['nTime']), d['n'], d['comment'])

    # First parse wallet to set correct coin type
    parse_wallet(db, item_callback)
    
    json_db['keys'] = []
    json_db['names'] = {}

    db.close()

    # Do real parse
    db = open_wallet(db_env, wallet)

    parse_wallet(db, item_callback)

    db.close()

    count = 0
    addrs = [];
    extra_addrs = [];
    for k in json_db['keys']:
        addr = k['addr']
        
        if addr in json_db['names'].keys():
            addrs.append(k['addr'])
        elif count > 3:
            extra_addrs.append(k['addr'])
        else:
            k["reserve"] = 1
            extra_addrs.append(k['addr'])
            count = count+1
    
    json_db['addrs'] = addrs
    json_db['extra_addrs'] = extra_addrs
    json_db['keys'] = [k for k in json_db['keys'] if ("reserve" in k and k["reserve"] == 1)]
    json_db['keys'] = json_db['keys'][0:3]


# download-blockchain-wallet.py -- Blockchain.info wallet file downloader
# Copyright (C) 2016, 2017 Christopher Gurnee
#
# This file is part of btcrecover.
#
# btcrecover is free software: you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version
# 2 of the License, or (at your option) any later version.
#
# btcrecover is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see http://www.gnu.org/licenses/

# If you find this program helpful, please consider a small
# donation to the developer at the following Bitcoin address:
#
#           3Au8ZodNHPei7MQiSVAWb7NB2yqsb48GW4
#
#                      Thank You!


# Performs a web request, adding the api_code and (if available) auth_token
blockchain_auth_token = None
def do_blockchain_request(query, body = None):
    global blockchain_auth_token
    
    if query != "sessions" and blockchain_auth_token is None: 
      blockchain_auth_token = do_blockchain_request_json("sessions", "")["token"]  # a POST request
        
    # The base URL
    BASE_URL = "https://blockchain.info/"
    # The api_code (as of Feb 2 2017)
    API_CODE = "1770d5d9-bcea-4d28-ad21-6cbd5be018a8"

    if body is None:
        assert "?" in query
        query += "&api_code=" + API_CODE
    req = urllib2.Request(BASE_URL + query)
    if body is not None:
        req.add_data((body+"&" if body else "") + "api_code=" + API_CODE)
    if blockchain_auth_token:
        req.add_header("authorization", "Bearer " + blockchain_auth_token)
    try:
        return urllib2.urlopen(req, cadefault=True)  # calls ssl.create_default_context() (despite what the docs say)
    except TypeError:
        return urllib2.urlopen(req)  # Python < 2.7.9 doesn't support the cadefault argument
#
# Performs a do_request(), decoding the result as json
def do_blockchain_request_json(query, body = None):
    return json.load(do_blockchain_request(query, body))


def download_blockchain_wallet(wallet_id, show_authorisation, show_2fa, show_done, do_sleep):
    wallet_id = str(uuid.UUID(wallet_id.strip()))
    
    def process_2FA(two_factor):
        try:
            # Send the 2FA to the server and download the wallet
            wallet_data = do_blockchain_request("wallet",
                "method=get-wallet&guid={}&payload={}&length={}"
                .format(wallet_id, two_factor, len(two_factor))
            ).read()
            
            if wallet_data:
                return last_step(wallet_data)

        except urllib2.HTTPError as e:
            print(e.read() + "\n", file=sys.stderr)
        
        show_2fa(process_2FA);
            
    def last_step(wallet_data):
        try:
            decoded_data = json.loads(wallet_data)
            if "version" in decoded_data and (str(decoded_data["version"]) == "2" or str(decoded_data["version"]) == "3"):
                payload = base64.b64decode(decoded_data["payload"])
                # Only send the necessary data, remove all other information
                payload = payload[0:32]
                
                iterations = decoded_data["pbkdf2_iterations"]
                show_done("$blockchain$v2$%s$%s$%s" % (
                    iterations, len(payload),
                    binascii.hexlify(payload).decode(("ascii"))))
                    
        except:
            traceback.print_exc()
    
    def check_auth():
        poll_data = do_blockchain_request_json("wallet/poll-for-session-guid?format=json")
        if "guid" in poll_data:
            # Try again to download the wallet (this shouldn't fail)
            wallet_data = do_blockchain_request_json(
                "wallet/{}?format=json".format(wallet_id)
            ).get("payload")
            
            if not wallet_data:
                show_2fa(process_2FA)
            else:
                last_step(wallet_data)
         
            return
            
        do_sleep(5, check_auth)
    
    # Try to download the wallet
    try:
        wallet_data = do_blockchain_request_json(
            "wallet/{}?format=json".format(wallet_id)
        ).get("payload")

    # If IP address / email verification is required
    except urllib2.HTTPError as e:
        error_msg = e.read()
        try:
            error_msg = json.loads(error_msg)["initial_error"]
        except: pass
        print(error_msg)
        if error_msg.lower().startswith("unknown wallet identifier"):
            sys.exit(1)

        # Wait for the user to complete the requested authorization
        print("Waiting for authorization (press Ctrl-C to give up)...")
        
        show_authorisation()
        do_sleep(5, check_auth)
        return
        

    if not wallet_data:
        show_2fa(process_2FA)
    else:
        last_step(wallet_data)








from optparse import OptionParser

def findWallets(foundWallet):
    global root
    wallet_paths = [os.path.expanduser("~/Library/Application Support/Bitcoin/wallet.dat"), os.path.expanduser("~/.bitcoin/wallet.dat")]
    if 'APPDATA' in os.environ:
        wallet_paths.push(os.path.join(os.environ['APPDATA'], "Bitcoin/wallet.dat"))

    for wallet_path in wallet_paths:
        if os.path.isfile(wallet_path):
            foundWallet(wallet_path)

    for os_root, dirnames, filenames in os.walk('/'):
        for filename in fnmatch.filter(filenames, 'wallet.dat'):
            foundWallet(os.path.join(os_root, filename))
        root.update()

    print("done")

def blockchainWalletIdInputFrame():
    global container, root
    if container:
        container.destroy()

    def do_sleep(time, callback):
        container.after(time*1000, callback)
        
    def startRecovery(): 
       download_blockchain_wallet(wallet_id.get(), blockchainAuthorisationFrame, blockchain2FAFrame, blockchainDoneFrame, do_sleep)

    container = tk.Frame(root)
    container.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=1, width=-20)
    
    message = tk.Message(container, text='First we will download the wallet from the blockchain service. Therefor you need to enter your Wallet ID of blockchain account, it looks like 9bb4c672-563e-4806-9012-a3e8f86a0eca. If you can\'t remember, you can recover it on https://blockchain.info/wallet/#/reminder.')
    message.bind("<Configure>", lambda e: message.configure(width=e.width-20))
    message.pack(fill=tk.X,padx=10,pady=20)
    
    wallet_id = tk.Entry(container)
    wallet_id.pack(fill=tk.X,padx=40,pady=20)
    wallet_id.bind("<Configure>", lambda e: wallet_id.configure(width=e.width-80))
    
    button = tk.Button(container, text='Recover this', width=25, command=startRecovery)
    button.pack()

def blockchainAuthorisationFrame():
    global container, root
    if container:
        container.destroy()
        
    container = tk.Frame(root)
    container.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=1, width=-20)
    
    message = tk.Message(container, text='Email approval is enabled on you wallet. You will get an email from Blockchain to authorize this login. By clicking on the link in that email, you can approve this login. So we are waiting for authorization...')
    message.bind("<Configure>", lambda e: message.configure(width=e.width-20))
    message.pack(fill=tk.X,padx=10,pady=20)
 
def blockchain2FAFrame(callback):
    global container, root
    if container:
        container.destroy()

    def entered2FA(): 
        callback(entry2fa.get())

    container = tk.Frame(root)
    container.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=1, width=-20)
    
    message = tk.Message(container, text='This wallet has two-factor authentication enabled. Please enter your 2FA code')
    message.bind("<Configure>", lambda e: message.configure(width=e.width-20))
    message.pack(fill=tk.X,padx=10,pady=20)
    
    entry2fa = tk.Entry(container)
    entry2fa.pack(fill=tk.X,padx=40,pady=20)
    entry2fa.bind("<Configure>", lambda e: entry2fa.configure(width=e.width-80))
    
    button = tk.Button(container, text='Submit', width=25, command=entered2FA)
    button.pack()   
  
def blockchainDoneFrame(wallet_data):
    global container, root
    if container:
        container.destroy()
        
    container = tk.Frame(root)
    container.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=1, width=-20)

    message = tk.Message(container, text='Success. You have retrieved the Blockchain info. Send the data below and a list of possible passwords to your recoverer. He will bruteforce your password for a fee of your BTC.')
    message.bind("<Configure>", lambda e: message.configure(width=e.width-20))
    message.pack(fill=tk.X,padx=10,pady=20)
    
    wallet_info = tk.Entry(container)
    wallet_info.pack(fill=tk.X,padx=40,pady=20)
    wallet_info.bind("<Configure>", lambda e: wallet_info.configure(width=e.width-80))
    wallet_info.insert(0, wallet_data);

def chooseMethodFrame():
    global container, root
    if container:
        container.destroy()

    container = tk.Frame(root)
    container.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=1, width=-20)

    text = tk.Message(container, text='The first step of recovery is getting information from your wallet in a secure way, allowing external parties to bruteforce your password. For this we will extract the necessary information from the wallet file without accessing or giving information that could give anybody access to the funds.')
    text.bind("<Configure>", lambda e: text.configure(width=e.width-20))
    text.pack(fill=tk.X,padx=10,pady=20)

    button = tk.Button(container, text='Select Bitcoin Core wallet', width=22, command=walletDetailsFrame)
    button.pack(fill=tk.X,padx=10,side=tk.LEFT)

    button = tk.Button(container, text='Search Bitcoin Core wallet', width=22, command=findWalletsFrame)
    button.pack(fill=tk.X,padx=10,side=tk.LEFT)
    
    button = tk.Button(container, text='Extract Blockchain wallet data', width=22, command=blockchainWalletIdInputFrame)
    button.pack(fill=tk.X,padx=10,side=tk.RIGHT)

def findWalletsFrame():
    global container, root
    if container:
        container.destroy()

    container = tk.Frame(root)
    container.pack(fill=tk.X,padx=10)
    saved_container = container

    searching = tk.Message(container, width=450, text='Busy with searching after wallets...')
    searching.pack(fill=tk.X,padx=10,pady=20,side=tk.BOTTOM)

    def callWrapper(file):
        def caller():
            return walletDetailsFrame(file)
        return caller;

    def foundWallet(file):
        if saved_container is not container:
            return;
            
        container2 = tk.Frame(container)
        container2.pack(fill=tk.X,padx=10)
    
        label = tk.Message(container2, width=250, text=file)
        label.pack(fill=tk.X,padx=10,side=tk.LEFT)

        button = tk.Button(container2, text='Recover this', width=25, command=callWrapper(file))
        button.pack(fill=tk.X,padx=10,side=tk.RIGHT)

    findWallets(foundWallet)
    searching.destroy()

def saveJSONFrame():
    global container, root, json_db

    wallet = tkFileDialog.asksaveasfilename(initialfile = "wallet.json",filetypes = (("Wallet info files","*.json"),("all files","*.*")))
    if(wallet):
        
        if container:
            container.destroy()

        container = tk.Frame(root)
        container.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=1, width=-20)

        label = tk.Message(container, text='Success. You have saved the wallet info file. Send this file and a list of possible passwords to your recoverer. He will bruteforce your password for a fee of your BTC.')
        label.bind("<Configure>", lambda e: label.configure(width=e.width-20))
        label.pack(fill=tk.X,padx=10,pady=20)

        with open(wallet, 'w') as outfile:
            json.dump(json_db, outfile)
    
def blockchain_callback(event):
    webbrowser.open_new("https://blockchain.info/address/"+event.widget.cget("text"))

def url_callback(event):
    webbrowser.open_new(event.widget.cget("text"))

def walletDetailsFrame(wallet=None):
    global container, root, json_db

    if not wallet:
        wallet = tkFileDialog.askopenfilename(title = "Select file",filetypes = (("Wallet files","wallet.dat"),("all files","*.*")))
    if wallet:
        db_env = create_env(wallet)
        read_wallet(json_db, db_env, wallet, True, True, "")

        if container:
            container.destroy()

        container = tk.Frame(root)
        container.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=1, width=-20)

        label2 = tk.Message(container, text='We have now extracted the necessary information. But you should check the following addresses. These are addresses that are in your wallet and according to your wallet has no funds. You click on the address and then check if the website says that the final balance is zero. Also there should be no transactions.')
        label2.bind("<Configure>", lambda e: label2.configure(width=e.width-20))
        label2.pack(fill=tk.X,padx=10,pady=20)

        for k in json_db["keys"]:
            label = tk.Label(container, text=k["addr"], fg="blue", cursor="hand2")
            label.pack()
            label.bind("<Button-1>", blockchain_callback)

        label = tk.Message(container, text='After you have done that, you can click on the following button to save the information file that you should send to your recoverer.')
        label.bind("<Configure>", lambda e: label.configure(width=e.width-20))
        label.pack(fill=tk.X,padx=10,pady=20)

        button = tk.Button(container, text='Save wallet.json', width=25, command=saveJSONFrame)
        button.pack()

    
container = False
def main():
    global root, container

    root = tk.Tk()
    root.title("BTC recovery")
    root.minsize(width=750,height=400)
    chooseMethodFrame()
    
    label = tk.Label(root, text='BTC recovery', font='Helvetica 14 bold')
    label.pack(fill=tk.X,pady=20,side=tk.TOP)

    label = tk.Label(root, text='https://cybergeek.be/index.php/bitcoin-recovery-service/', fg="blue")
    label.bind("<Button-1>", url_callback)
    label.pack(fill=tk.X,padx=10,pady=20,side=tk.BOTTOM)

    root.mainloop()

if __name__ == '__main__':
    main()
