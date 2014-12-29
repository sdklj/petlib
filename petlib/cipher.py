from bindings import _FFI, _C
from binascii import hexlify

import pytest


def _check(return_val):
    """Checks the return code of the C calls"""
    if type(return_val) is int and return_val == 1:
      return
    if type(return_val) is bool and return_val == True:
      return

    raise Exception("Cipher exception") 

class Cipher(object):
    """ A class representing a symmetric cipher and mode.

    Example:
        
        >>> aes = Cipher("AES-128-CTR")
        >>> enc = aes.enc(key="AAAAAAAAAAAAAAAA", iv="AAAAAAAAAAAAAAAA")
        >>> ref = "Hello World"
        >>> ciphertext = enc.update(ref)
        >>> ciphertext += enc.finalize()
        >>> hexlify(ciphertext)
        'b0aecdc6347177db8091be'
        >>> dec = aes.dec(key="AAAAAAAAAAAAAAAA", iv="AAAAAAAAAAAAAAAA")
        >>> plaintext = dec.update(ciphertext)
        >>> plaintext += dec.finalize()
        >>> plaintext == ref
        True

    """

    @staticmethod
    def aes_128_gcm():
        return Cipher(None, _C.EVP_aes_128_gcm())

    @staticmethod
    def aes_192_gcm():
        return Cipher(None, _C.EVP_aes_192_gcm())

    @staticmethod
    def aes_256_gcm():
        return Cipher(None, _C.EVP_aes_256_gcm())

        
    __slots__ = ["alg", "gcm"]

    def __init__(self, name, _alg=None):
        """Initialize the cipher by name"""

        if _alg:
            self.alg = _alg
            self.gcm = True
            return
        else:
            self.alg = _C.EVP_get_cipherbyname(name)
            self.gcm = False
            if self.alg == _FFI.NULL:
                raise Exception("Unknown cipher: %s" % name )

        if "gcm" in name.lower():
            self.gcm = True
        
        if "ccm" in name.lower():
            raise Exception("CCM mode not supported")

    def len_IV(self):
        """Return the Initialization Vector length in bytes."""
        return int(self.alg.iv_len)
    def len_key(self):
        """Return the secret key length in bytes."""
        return int(self.alg.key_len)
    def len_block(self):
        """Return the block size in bytes."""
        return int(self.alg.block_size)
    def get_nid(self):
        """Return the OpenSSL nid of the cipher and mode."""
        return int(self.alg.nid)

    def op(self, key, iv, enc=1):
        c_op = CipherOperation()
        _check( len(key) == self.len_key())
        _check( enc in [0,1] )
       
        if not self.gcm:
            _check( len(iv) == self.len_IV())
            _check( _C.EVP_CipherInit_ex(c_op.ctx, 
                self.alg,  _FFI.NULL, key, iv, enc) )
        else:
            _check( _C.EVP_CipherInit_ex(c_op.ctx, 
                self.alg,  _FFI.NULL, _FFI.NULL, _FFI.NULL, enc) )

            # assert len(iv) <= self.len_block()

            _check( _C.EVP_CIPHER_CTX_ctrl(c_op.ctx, 
                _C.EVP_CTRL_GCM_SET_IVLEN, len(iv), _FFI.NULL))

            _check( _C.EVP_CipherInit_ex(c_op.ctx, 
                _FFI.NULL,  _FFI.NULL, key, iv, enc) )

        c_op.cipher = self
        return c_op

    def enc(self, key, iv):
        """Initializes an encryption engine with the cipher with a specific key and Initialization Vector (IV). 
        Returns the CipherOperation engine."""
        return self.op(key, iv, enc=1)

    def dec(self, key, iv):
        """Initializes a decryption engine with the cipher with a specific key and Initialization Vector (IV). 
        Returns the CipherOperation engine."""
        return self.op(key, iv, enc=0)

    def __del__(self):
        pass

    def quick_gcm_enc(self, key, iv, msg, assoc=None, tagl=16):
        """One operation GCM encryption"""
        enc = self.enc(key, iv)
        if assoc:
            dec.update_associated(assoc)
        ciphertext = enc.update(msg)
        enc.finalize()
        tag = enc.get_tag(tagl)
        return (ciphertext, tag)

    def quick_gcm_dec(self, key, iv, cip, tag, assoc=None):
        """One operation GCM decrypt"""
        dec = self.dec(key, iv)
        if assoc:
            dec.update_associated(assoc)
        plain = dec.update(cip)
        dec.set_tag(tag)
        
        dec.finalize()
        return plain
                

class CipherOperation(object):

    __slots__ = ["ctx", "cipher"]

    def __init__(self):
        self.ctx = _C.EVP_CIPHER_CTX_new()
        _C.EVP_CIPHER_CTX_init(self.ctx)
        self.cipher = None
        
    #def control(self, ctype, arg, ptr):
    #    """Passes an OpenSSL control message to the CipherOpenration engine."""
    #    ret = int(_C.EVP_CIPHER_CTX_ctrl(self.ctx, ctype, arg, ptr))
    #    return ret

    def update_associated(self, data):
        """Processes some associated data, and returns nothing."""
        outl = _FFI.new("int *")
        _check( _C.EVP_CipherUpdate(self.ctx, _FFI.NULL, outl, data, len(data)))
    
    def update(self, data):
        """Processes some data, and returns a partial result."""
        block_len = self.cipher.len_block()
        alloc_len = len(data) + block_len - 1
        outl = _FFI.new("int *")
        outl[0] = alloc_len
        out = _FFI.new("unsigned char[]", alloc_len)
        _check( _C.EVP_CipherUpdate(self.ctx, out, outl, data, len(data)))
        ret = str(_FFI.buffer(out)[:int(outl[0])])
        return ret

    def finalize(self):
        """Finalizes the operation and may return some additional data"""
        block_len = self.cipher.len_block()
        alloc_len = block_len
        outl = _FFI.new("int *")
        outl[0] = alloc_len
        out = _FFI.new("unsigned char[]", alloc_len)

        _check( _C.EVP_CipherFinal_ex(self.ctx, out, outl) )
        if outl[0] == 0:
            return ''

        ret = str(_FFI.buffer(out)[:int(outl[0])])
        return ret


    def get_tag(self, tag_len = 16):
        tag = _FFI.new("unsigned char []", tag_len)
        ret =  _C.EVP_CIPHER_CTX_ctrl(self.ctx, _C.EVP_CTRL_GCM_GET_TAG, tag_len, tag)
        _check( ret )
        s = str(_FFI.buffer(tag)[:])
        return s
        

    def set_tag(self, tag):
        _check( _C.EVP_CIPHER_CTX_ctrl(self.ctx, _C.EVP_CTRL_GCM_SET_TAG, len(tag), tag))

    def __del__(self):
        _check( _C.EVP_CIPHER_CTX_cleanup(self.ctx) )
        _C.EVP_CIPHER_CTX_free(self.ctx)


def test_aes_init():
    aes = Cipher("AES-128-CBC")
    assert aes.alg != _FFI.NULL
    assert aes.len_IV() == 16
    assert aes.len_block() == 16
    assert aes.len_key() == 16
    assert aes.get_nid() == 419
    del aes


def test_errors():
    with pytest.raises(Exception) as excinfo:
        aes = Cipher("AES-128-XXF")
    assert 'Unknown' in str(excinfo.value)

def test_aes_enc():
    aes = Cipher("AES-128-CBC")
    enc = aes.op(key="A"*16, iv="A"*16)

    ref = "Hello World" * 10000

    ciphertext = enc.update(ref)
    ciphertext += enc.finalize()

    dec = aes.op(key="A"*16, iv="A"*16, enc=0)
    plaintext = dec.update(ciphertext)
    plaintext += dec.finalize()
    assert plaintext == ref

def test_aes_ctr():
    aes = Cipher("AES-128-CTR")
    enc = aes.op(key="A"*16, iv="A"*16)

    ref = "Hello World" * 10000

    ciphertext = enc.update(ref)
    ciphertext += enc.finalize()

    dec = aes.op(key="A"*16, iv="A"*16, enc=0)
    plaintext = dec.update(ciphertext)
    plaintext += dec.finalize()
    assert plaintext == ref

def test_aes_ops():
    aes = Cipher("AES-128-CTR")
    enc = aes.enc(key="A"*16, iv="A"*16)

    ref = "Hello World" * 10000

    ciphertext = enc.update(ref)
    ciphertext += enc.finalize()

    dec = aes.dec(key="A"*16, iv="A"*16)
    plaintext = dec.update(ciphertext)
    plaintext += dec.finalize()
    assert plaintext == ref

def test_aes_gcm_encrypt():
    aes = Cipher.aes_128_gcm()
    assert aes.gcm

    print aes.len_IV()
    enc = aes.op(key="A"*16, iv="A"*16)

    enc.update_associated("Hello")
    ciphertext = enc.update("World!")
    c2 = enc.finalize()
    assert c2 == ''

    tag = enc.get_tag(16)
    assert len(tag) == 16

def test_aes_gcm_encrypt_192():
    aes = Cipher.aes_192_gcm()
    assert aes.gcm

    print aes.len_IV()
    enc = aes.op(key="A"*(192/8), iv="A"*16)

    enc.update_associated("Hello")
    ciphertext = enc.update("World!")
    c2 = enc.finalize()
    assert c2 == ''

    tag = enc.get_tag(16)
    assert len(tag) == 16


def test_aes_gcm_encrypt_256():
    aes = Cipher.aes_256_gcm()
    assert aes.gcm

    print aes.len_IV()
    enc = aes.op(key="A"*(256/8), iv="A"*16)

    enc.update_associated("Hello")
    ciphertext = enc.update("World!")
    c2 = enc.finalize()
    assert c2 == ''

    tag = enc.get_tag(16)
    assert len(tag) == 16


@pytest.fixture
def aesenc():
    aes = Cipher.aes_128_gcm()
    assert aes.gcm

    print aes.len_IV()
    enc = aes.op(key="A"*16, iv="A"*16)

    enc.update_associated("Hello")
    ciphertext = enc.update("World!")
    c2 = enc.finalize()
    assert c2 == ''

    tag = enc.get_tag(16)
    assert len(tag) == 16

    return (aes,enc, ciphertext, tag)

def test_gcm_dec(aesenc):
    aes, enc, ciphertext, tag = aesenc
    dec = aes.dec(key="A"*16, iv="A"*16)
    dec.update_associated("Hello")
    plaintext = dec.update(ciphertext)

    dec.set_tag(tag)

    dec.finalize()

    assert plaintext == "World!"

def test_gcm_dec_badassoc(aesenc):
    aes, enc, ciphertext, tag = aesenc

    dec = aes.dec(key="A"*16, iv="A"*16)
    dec.update_associated("H4llo")
    plaintext = dec.update(ciphertext)

    dec.set_tag(tag)

    with pytest.raises(Exception) as excinfo:
        dec.finalize()
    assert "Cipher" in str(excinfo.value)

def test_gcm_dec_badkey(aesenc):
    aes, enc, ciphertext, tag = aesenc

    dec = aes.dec(key="B"*16, iv="A"*16)
    dec.update_associated("Hello")
    plaintext = dec.update(ciphertext)

    dec.set_tag(tag)

    with pytest.raises(Exception) as excinfo:
        dec.finalize()
    assert "Cipher" in str(excinfo.value)

def test_gcm_dec_badiv(aesenc):
    aes, enc, ciphertext, tag = aesenc
    dec = aes.dec(key="A"*16, iv="B"*16)
    dec.update_associated("Hello")
    plaintext = dec.update(ciphertext)

    dec.set_tag(tag)

    with pytest.raises(Exception) as excinfo:
        dec.finalize()
    assert "Cipher" in str(excinfo.value)

def test_aes_gcm_byname():
    aes = Cipher("aes-128-gcm")
    assert aes.gcm

    print aes.len_IV()
    enc = aes.op(key="A"*16, iv="A"*16)

    enc.update_associated("Hello")
    ciphertext = enc.update("World!")
    c2 = enc.finalize()
    assert c2 == ''

    tag = enc.get_tag(16)
    assert len(tag) == 16

    dec = aes.dec(key="A"*16, iv="A"*16)
    dec.update_associated("Hello")
    plaintext = dec.update(ciphertext)

    dec.set_tag(tag)

    dec.finalize()

    assert plaintext == "World!"

def test_aes_gcm_different_IV():
    aes = Cipher("aes-128-gcm")

    enc = aes.op(key="A"*16, iv="A"*16)
    enc.update_associated("Hello")
    ciphertext = enc.update("World!")
    c2 = enc.finalize()
    tag = enc.get_tag(16)

    enc = aes.op(key="A"*16, iv="A"*16)
    enc.update_associated("Hello")
    ciphertext2 = enc.update("World!")
    c2 = enc.finalize()
    tag2 = enc.get_tag(16)

    enc = aes.op(key="A"*16, iv="B"*16)
    enc.update_associated("Hello")
    ciphertext3 = enc.update("World!")
    c2 = enc.finalize()
    tag3 = enc.get_tag(16)

    assert ciphertext == ciphertext2
    assert ciphertext != ciphertext3

def test_quick():
    aes = Cipher("aes-128-gcm")
    c, t = aes.quick_gcm_enc("A"*16, "A"*16, "Hello")
    p = aes.quick_gcm_dec("A"*16, "A"*16, c, t)
    assert p == "Hello"
