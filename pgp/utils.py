# python-pgp A Python OpenPGP implementation                                                                         
# Copyright (C) 2014 Richard Mitchell
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from base64 import b64encode
import hashlib
import math

from pgpdump.utils import crc24

from Crypto import Hash
from Crypto import PublicKey
from Crypto.Random import random
from Crypto.Signature import PKCS1_v1_5
from Crypto.Util.number import bytes_to_long
from Crypto.Util.number import GCD
from Crypto.Util.number import long_to_bytes
from pgpdump.utils import get_int2
from pgpdump.utils import get_mpi

from pgp.exceptions import PublicKeyAlgorithmCannotSign
from pgp.exceptions import UnsupportedDigestAlgorithm
from pgp.exceptions import UnsupportedPublicKeyAlgorithm


armored_key_format = u"""
-----BEGIN PGP PUBLIC KEY BLOCK-----
Version: {version}
Charset: ascii-us

{data}
={checksum}
-----END PGP PUBLIC KEY BLOCK-----
"""


def bytes_to_armor(byte_data, version_string=None, comment=None):
    encoded_data = b64encode(byte_data)
    data_lines = []
    for l in range(int(math.ceil(len(encoded_data) / 72.0))):
        data_lines.append(encoded_data[l * 72:(l * 72) + 72])
    formatted_data = u'\n'.join(data_lines)
    checksum_value = crc24(byte_data)
    checksum = bytearray([
            (checksum_value >> (i * 8)) & 0xff
            for i in (2, 1, 0)
            ])
    checksum = b64encode(checksum)

    return armored_key_format.strip().format(
        version=version_string,
        data=formatted_data,
        checksum=checksum
        )


def sign_hash(pub_algorithm_type, secret_key, hash_, k=None):
    if pub_algorithm_type in (1, 3):
        # RSA
        sig_string = PKCS1_v1_5.new(secret_key).sign(hash_)
        return (bytes_to_long(sig_string),)
    elif pub_algorithm_type == 20:
        # ELG
        # TODO: Should only be allowed for test purposes
        if k is None:
            while 1:
                # This can be pretty darn slow
                k = random.StrongRandom().randint(1, secret_key.p - 1)
                if GCD(k, secret_key.p - 1) == 1:
                    break
            print k
        # TODO: Remove dependence on undocumented method
        sig_string = PKCS1_v1_5.EMSA_PKCS1_V1_5_ENCODE(
                            hash_, secret_key.size())
        return secret_key.sign(sig_string, k)
    elif pub_algorithm_type == 17:
        q = secret_key.q
        qbits = int(math.floor(float(math.log(q, 2)))) + 1
        qbytes = int(math.ceil(qbits / 8.0))
        if k is None:
            k = random.StrongRandom().randint(1, q - 1)

        digest = hash_.digest()[:qbytes]
        return secret_key.sign(bytes_to_long(digest), k)
    else:
        # TODO: complete
        raise ValueError


def verify_hash(pub_algorithm_type, public_key, hash_, values):
    if pub_algorithm_type in (1, 3):
        # RSA
        s = long_to_bytes(values[0])
        return PKCS1_v1_5.new(public_key).verify(hash_, s)
    elif pub_algorithm_type == 20:
        # ELG
        # TODO: Remove dependence on undocumented method
        sig_string = PKCS1_v1_5.EMSA_PKCS1_V1_5_ENCODE(
                            hash_, public_key.size())
        return public_key.verify(sig_string, values)
    elif pub_algorithm_type == 17:
        # DSA
        q = public_key.q
        if q % 8:
            # TODO: complete this
            raise ValueError
        qbits = int(math.floor(float(math.log(q, 2)))) + 1
        qbytes = int(math.ceil(qbits / 8.0))

        digest = hash_.digest()
        # Discard empty leading bytes
        start = 0
        while digest[start] == '\x00':
            start += 1
        digest = digest[start:start + qbytes]
        return public_key.verify(bytes_to_long(digest), values)
    else:
        # TODO: complete this
        raise ValueError


def get_hash_instance(type_):
    """Given a hash type code, returns a new hash instance for that
    type.
    """

    if type_ == 1:
        return Hash.MD5.new()
    elif type_ == 2:
        return Hash.SHA.new()
    elif type_ == 3:
        return Hash.RIPEMD.new()
    elif type_ == 8:
        return Hash.SHA256.new()
    elif type_ == 9:
        try:
            return Hash.SHA384.new()  # @UndefinedVariable
        except AttributeError:
            return hashlib.new('sha384')
    elif type_ == 10:
        try:
            return Hash.SHA512.new()  # @UndefinedVariable
        except AttributeError:
            return hashlib.new('sha512')
    elif type_ == 11:
        try:
            return Hash.SHA224.new()  # @UndefinedVariable
        except AttributeError:
            return hashlib.new('sha224')
    else:
        raise UnsupportedDigestAlgorithm(type_)


def get_public_key_constructor(type_):
    """Given a public key type code, returns a function which may be
    used to construct a new instance of that key.
    """
    if type_ == 1:
        # rsa encrypt or sign
        return PublicKey.RSA.construct
    elif type_ == 2:
        # rsa encrypt only
        # invalid for signing
        raise PublicKeyAlgorithmCannotSign(2)
    elif type_ == 3:
        # rsa sign only
        return PublicKey.RSA.construct
    elif type_ == 16:
        # elgamel encrypt only
        # invalid for signing
        raise PublicKeyAlgorithmCannotSign(16)
    elif type_ == 17:
        # dsa
        return PublicKey.DSA.construct
    elif type_ == 18:
        # ec
        # invalid for signing
        raise PublicKeyAlgorithmCannotSign(18)
    elif type_ == 19:
        # ecdsa
        raise UnsupportedPublicKeyAlgorithm(19)
    elif type_ == 20:
        # elgamel encrypt or sign
        return PublicKey.ElGamal.construct
    elif type_ == 21:
        # diffie-hellman
        # invalid for signing
        raise PublicKeyAlgorithmCannotSign(21)
    elif type_ == 105:
        # EDDSA
        # Experimental
        raise UnsupportedPublicKeyAlgorithm(105)
    else:
        raise UnsupportedPublicKeyAlgorithm(type_)


def get_bitlen(public_key_data):
    pub_algorithm_type = public_key_data['pub_algorithm_type']
    if pub_algorithm_type in (1, 3):
        n = public_key_data['modulus']
    elif pub_algorithm_type == 17:
        n = public_key_data['prime']
    elif pub_algorithm_type in (16, 20):
        n = public_key_data['prime']

    return int(math.ceil(float(math.log(n, 2))))


def hash_key(hash_, key_packet_data):
    """Adds key data to a hash for signature comparison."""

    key_length = len(key_packet_data)
    hash_.update('\x99')
    hash_.update(int_to_2byte(key_length))
    hash_.update(key_packet_data)


def packet_type_from_first_byte(byte_):
    if byte_ & 0x7f:
        return byte_ & 0x3f
    return (byte_ & 0x3f) >> 2


def hash_user_data(hash_, target_type, target_packet_data, signature_version):
    """Adds user attribute & user id packets to a hash for signature
    comparison.
    """

    if target_type == 13:
        if signature_version >= 4:
            hash_.update(bytearray(['\xb4']))
            hash_.update(int_to_4byte(len(target_packet_data)))
        hash_.update(target_packet_data)
    elif target_type == 17:
        if signature_version >= 4:
            hash_.update(bytearray(['\xd1']))
            hash_.update(int_to_4byte(len(target_packet_data)))
        hash_.update(target_packet_data)


def hash_packet_for_signature(public_key_packet_data, target_type,
                              packet_data, signature_type, signature_version,
                              hash_algorithm_type, signature_creation_time,
                              pub_algorithm_type, hashed_subpacket_data=None):
    hash_ = get_hash_instance(hash_algorithm_type)

    if signature_type in (0x1f, 0x20):
        hash_key(hash_, public_key_packet_data)
    elif signature_type in (0x18, 0x19, 0x28):
        hash_key(hash_, public_key_packet_data)
        hash_key(hash_, packet_data)
    else:
        hash_key(hash_, public_key_packet_data)
        hash_user_data(hash_, target_type, packet_data, signature_version)

    if signature_version >= 4:
        hash_.update(bytearray([signature_version]))
    hash_.update(bytearray([signature_type]))
    if signature_version < 4:
        hash_.update(int_to_4byte(signature_creation_time))
    else:
        hash_.update(bytearray([pub_algorithm_type]))
        hash_.update(bytearray([hash_algorithm_type]))
        hashed_subpacket_length = len(hashed_subpacket_data)
        hash_.update(int_to_2byte(hashed_subpacket_length))
        hash_.update(hashed_subpacket_data)
        hash_.update(bytearray([signature_version]))
        hash_.update(bytearray(['\xff']))
        hash_.update(int_to_4byte(hashed_subpacket_length + 6))

    return hash_


def int_to_2byte(i):
    """Given an integer, return a bytearray of its short, unsigned
    representation, big-endian.
    """

    return bytearray([
            (i >> 8) & 0xff,
            i & 0xff
        ])


def int_to_4byte(i):
    """Given an integer, return a bytearray of its unsigned integer
    representation, big-endian.
    """

    return bytearray([
            (i >> 24) & 0xff,
            (i >> 16) & 0xff,
            (i >> 8) & 0xff,
            i & 0xff
        ])


def int_to_8byte(i):
    """Given an integer, return a bytearray of its unsigned integer
    representation, big-endian.
    """

    return bytearray([
            (i >> 56) & 0xff,
            (i >> 48) & 0xff,
            (i >> 40) & 0xff,
            (i >> 32) & 0xff,
            (i >> 24) & 0xff,
            (i >> 16) & 0xff,
            (i >> 8) & 0xff,
            i & 0xff
        ])


def int_to_s2k_count(i):
    if i < 1024:
        raise ValueError(i)
    if i > 65011712:
        raise ValueError(i)
    shift = int(math.floor(math.log(i, 2))) - 4
    if i & ((1 << shift) - 1):
        raise ValueError(i)
    bits = (i >> shift) & 15
    return ((shift - 6) << 4) + bits


def int_to_mpi(i):
    if i < 0:
        raise ValueError(i)
    elif i == 0:
        return bytearray([0, 0])
    bits_required = int(math.floor(float(math.log(i, 2)))) + 1
    bytes_required = int(math.ceil(bits_required / 8.0))
    result = bytearray() + int_to_2byte(bits_required)
    for b in range(bytes_required - 1, -1, -1):
        result.append((i >> (b * 8)) & 0xff)
    return result


MAX_PACKET_LENGTH = 4294967295


def new_packet_length_to_bytes(data_length, allow_partial):
    result = bytearray()
    remaining = 0
    if data_length < 192:
        # one-octet body length
        result.append(data_length)
    elif data_length < 8384:
        # two-octet body length
        stored_length = data_length - 192
        result.append((stored_length >> 8) + 192)
        result.append(stored_length & 0xff)
    elif data_length <= MAX_PACKET_LENGTH:
        # five-octet body length
        result.append(0xff)
        result.append((data_length >> 24) & 0xff)
        result.append((data_length >> 16) & 0xff)
        result.append((data_length >> 8) & 0xff)
        result.append(data_length & 0xff)
    elif allow_partial:
        # 0x1e is the maximum length: 0x1f + 0xe0 = 0xff which is the same as
        # the five-octet length marker.
        result.append(
            0xe0 +  # Partial marker
            0x1e    # log(partial length, 2)
            )
        remaining = data_length - (2 ** 0x1e)
    else:
        raise ValueError((
                'Cannot store data longer than {0} for subpackets or non-data '
                'packets.').format(
                    MAX_PACKET_LENGTH
                ))

    return result, remaining


def old_packet_length_to_bytes(data_length):
    length_type = 0
    if data_length < 256:
        length_type = 0
        length_bytes = [data_length]
    elif data_length < 65536:
        length_type = 1
        length_bytes = [data_length >> 8,
                        data_length & 0xff]
    elif length_type < 16777216:
        length_type = 2
        length_bytes = [data_length >> 24,
                        (data_length >> 16) & 0xff,
                        (data_length >> 8) & 0xff,
                        data_length & 0xff]
    else:
        length_type = 3
        length_bytes = []
    return length_bytes


def hex_to_bytes(hex_val, expected_length):
    result = bytearray([0] * expected_length)
    for i in range(len(hex_val) / 2):
        idx = i * 2
        result.append(int(hex_val[idx:idx + 2], 16))
    return result[-expected_length:]


def bytearray_to_hex(arr, expected=None):
    result = ''.join(list(map(
                    lambda i: '{:02x}'.format(i),
                    arr)
                )
            ).upper()
    if expected is not None:
        if len(result) < expected:
            result = ('0' * len(result) - expected) + result
        else:
            result = result[-1 * expected:]
    return result


def compare_packets(packet1, packet2):
    c = cmp(packet1.raw, packet2.raw)
    if c:
        return c
    return cmp(packet1.data, packet2.data)


def sort_key(packets):
    return sorted(packets, cmp=compare_packets)


def concat_key(packets):
    buf = bytearray()
    for packet in packets:
        packet_length = len(packet.data)
        buf.append(packet.raw)
        buf.extend([
            (packet_length >> 24) & 0xff,
            (packet_length >> 16) & 0xff,
            (packet_length >> 8) & 0xff,
            packet_length & 0xff
            ])
        buf.extend(packet.data)
    return buf


def hash_key_data(packets):
    canonical_key_data = concat_key(sort_key(packets))
    if not canonical_key_data:
        return bytes('')
    return bytearray(Hash.MD5.new(canonical_key_data).hexdigest())


def get_signature_values(signature_packet_data):
    """Get the actual public key signature values from the signature
    packet data.
    """

    data = signature_packet_data

    sig_version = data[0]
    offset = 1
    if sig_version in (2, 3):
        offset += 1  # marker
        offset += 1  # signature type
        offset += 4  # creation time
        offset += 8  # key id
        offset += 1  # pub algorithm
        offset += 1  # hash algorithm
        offset += 2  # hash2
    elif sig_version >= 4:
        offset += 1  # signature type
        offset += 1  # pub algorithm
        offset += 1  # hash algorithm

        # hashed subpackets
        length = get_int2(data, offset)
        offset += 2
        offset += length

        # unhashed subpackets
        length = get_int2(data, offset)
        offset += 2
        offset += length

        # hash2
        offset += 2

    data_len = len(data)
    result = []
    while offset < data_len:
        mpi, o = get_mpi(data, offset)
        offset += o
        result.append(mpi)

    return result