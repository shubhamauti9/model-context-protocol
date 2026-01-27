import os
import struct
import time
import base64
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

key = os.getenv("ENCRYPTION_KEY", "").encode() #key in byte encoded format
if not key:
    # Fallback or warning - for now just keeping it empty as per original behavior but safer
    pass

iv = os.getenv("ENCRYPTION_IV", "").encode() #iv in byte encoded format

def encrypt(plaintext: bytes):
    padder = padding.PKCS7(128).padder()
    padded_data = padder.update(plaintext) + padder.finalize()

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(padded_data) + encryptor.finalize()
    encoded = base64.b64encode(ciphertext)
    return encoded.decode()

def decrypt(ciphertext: str):
    if not ciphertext:
        return b''

    try:
        ciphertext_bytes = base64.b64decode(ciphertext)
    except Exception as e:
        raise ValueError(f"Failed to decode base64 ciphertext: {e}")

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()
    try:
        padded_plaintext = decryptor.update(ciphertext_bytes) + decryptor.finalize()
    except ValueError as e:
        raise ValueError(f"Decryption failed : {e}")

    unpadder = padding.PKCS7(128).unpadder()
    plaintext = unpadder.update(padded_plaintext) + unpadder.finalize()
    return plaintext

def generateiv():
    timestamp = int(time.time() * 1_000_000)
    ts_bytes = struct.pack('>Q', timestamp)
    random_bytes = os.urandom(8)
    iv = ts_bytes + random_bytes
    return iv