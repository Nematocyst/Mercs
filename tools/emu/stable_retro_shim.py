"""Minimal stand-in for stable_retro: drives the genesis_plus_gx libretro core directly through ctypes.

Why: the stable_retro wheel is built for Python 3.12 only, but its Genesis core is a plain C library that any
Python can load. This module offers the subset of the stable_retro API the Buck Rogers scripts use:
  env = make(game=NAME); obs, info = env.reset(); obs, r, term, trunc, info = env.step(action12)
  env.get_ram()                         -> numpy uint8 copy of 64 KB work RAM, word-swapped like stable_retro
  env.em.get_state() / set_state(b)     -> libretro serialize / unserialize (same bytes as stable_retro states)
  env.unwrapped.data.memory.extract(0xFF0000+a, '|u1') / assign(0xFF0000+a, '|u1', v)   (logical byte order)
  env.screen()                          -> current frame as an RGB numpy array (for the rare screenshot)
Button order = stable_retro's: B, A, MODE, START, UP, DOWN, LEFT, RIGHT, C, Y, X, Z (= libretro joypad ids 0-11).
Games: register(name, rom_path); the original ROM is pre-registered as BuckRogersCountdownToDoomsday-Genesis-v0.
Core path: $GPGX_CORE or ./cores/genesis_plus_gx_libretro.so next to this file. One emulator per process.
"""
import ctypes as C, os, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.environ.get('GPGX_CORE', os.path.join(HERE, 'cores', 'genesis_plus_gx_libretro.so'))
GAMES = {'BuckRogersCountdownToDoomsday-Genesis-v0':
         os.environ.get('BR_ROM', '/mnt/user-data/uploads/Buck_Rogers_-_Countdown_to_Doomsday__USA__Europe_.md')}
SYSDIR = os.path.join(HERE, 'retro_sys'); os.makedirs(SYSDIR, exist_ok=True)


def register(name, rom_path): GAMES[name] = os.path.abspath(rom_path)


class _GameInfo(C.Structure):
    _fields_ = [('path', C.c_char_p), ('data', C.c_void_p), ('size', C.c_size_t), ('meta', C.c_char_p)]


ENV_CB = C.CFUNCTYPE(C.c_bool, C.c_uint, C.c_void_p)
VIDEO_CB = C.CFUNCTYPE(None, C.c_void_p, C.c_uint, C.c_uint, C.c_size_t)
AUDIO_CB = C.CFUNCTYPE(None, C.c_int16, C.c_int16)
AUDIOB_CB = C.CFUNCTYPE(C.c_size_t, C.c_void_p, C.c_size_t)
POLL_CB = C.CFUNCTYPE(None)
LOG_CB = C.CFUNCTYPE(None, C.c_int, C.c_char_p)       # variadic in C; extra args are ignored
INPUT_CB = C.CFUNCTYPE(C.c_int16, C.c_uint, C.c_uint, C.c_uint, C.c_uint)

_lib = None; _state = {}


def _load_core():
    global _lib
    if _lib: return _lib
    lib = C.CDLL(CORE)
    st = _state; st['buttons'] = [0] * 16; st['fmt'] = 0; st['frame'] = None; st['vars'] = {}
    st['log'] = LOG_CB(lambda level, fmt: None)
    sysdir = C.create_string_buffer(SYSDIR.encode() + b'\0'); st['sysdir'] = sysdir   # must outlive the core

    def env_cb(cmd, data):
        if cmd == 3:                                   # GET_CAN_DUPE
            C.cast(data, C.POINTER(C.c_bool))[0] = True; return True
        if cmd in (9, 31):                             # GET_SYSTEM_DIRECTORY / GET_SAVE_DIRECTORY
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.addressof(sysdir); return True
        if cmd == 10:                                  # SET_PIXEL_FORMAT
            st['fmt'] = C.cast(data, C.POINTER(C.c_int))[0]; return True
        if cmd == 16 and data:                         # SET_VARIABLES: {key, "Desc; default|opt|..."}[] -> defaults
            arr = C.cast(data, C.POINTER(C.c_char_p * 2)); i = 0
            while arr[i][0]:
                key, val = arr[i][0], arr[i][1] or b''
                default = val.split(b'; ', 1)[-1].split(b'|')[0]
                st['vars'][key] = C.create_string_buffer(default)       # kept alive for the core
                i += 1
            return True
        if cmd == 15 and data:                         # GET_VARIABLE: answer with the default (core needs a value)
            v = C.cast(data, C.POINTER(C.c_void_p * 2))[0]
            key = C.string_at(v[0]) if v[0] else b''
            if key in st['vars']:
                v[1] = C.addressof(st['vars'][key]); return True
            return False
        if cmd == 27 and data:                         # GET_LOG_INTERFACE: this core build calls log_cb unconditionally
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(st['log'], C.c_void_p).value; return True
        if cmd == 17:                                  # GET_VARIABLE_UPDATE
            C.cast(data, C.POINTER(C.c_bool))[0] = False; return True
        return False                                   # everything else: unsupported -> core defaults

    def video_cb(data, w, h, pitch):
        if data: st['frame'] = (C.string_at(data, pitch * h), w, h, pitch)

    def input_cb(port, device, index, id_):
        return st['buttons'][id_] if port == 0 and device == 1 and id_ < 16 else 0

    st['cbs'] = (ENV_CB(env_cb), VIDEO_CB(video_cb), AUDIO_CB(lambda l, r: None),
                 AUDIOB_CB(lambda d, n: n), POLL_CB(lambda: None), INPUT_CB(input_cb))
    lib.retro_set_environment(st['cbs'][0]); lib.retro_init()
    lib.retro_set_video_refresh(st['cbs'][1]); lib.retro_set_audio_sample(st['cbs'][2])
    lib.retro_set_audio_sample_batch(st['cbs'][3]); lib.retro_set_input_poll(st['cbs'][4])
    lib.retro_set_input_state(st['cbs'][5])
    lib.retro_get_memory_data.restype = C.c_void_p; lib.retro_get_memory_size.restype = C.c_size_t
    lib.retro_serialize_size.restype = C.c_size_t
    lib.retro_serialize.argtypes = [C.c_void_p, C.c_size_t]; lib.retro_serialize.restype = C.c_bool
    lib.retro_unserialize.argtypes = [C.c_void_p, C.c_size_t]; lib.retro_unserialize.restype = C.c_bool
    lib.retro_load_game.argtypes = [C.POINTER(_GameInfo)]; lib.retro_load_game.restype = C.c_bool
    _lib = lib; return lib


class _Memory:
    def __init__(self, env): self.env = env
    def extract(self, addr, fmt='|u1'):
        assert fmt == '|u1' and 0xFF0000 <= addr <= 0xFFFFFF
        return self.env._ram[(addr - 0xFF0000) ^ 1]
    def assign(self, addr, fmt, value):
        assert fmt == '|u1' and 0xFF0000 <= addr <= 0xFFFFFF
        self.env._ram[(addr - 0xFF0000) ^ 1] = value & 0xFF


class _Em:
    def __init__(self, env): self.env = env
    def get_state(self):
        lib = self.env._lib; n = lib.retro_serialize_size(); buf = C.create_string_buffer(n)
        assert lib.retro_serialize(buf, n); return buf.raw
    def set_state(self, data):
        buf = C.create_string_buffer(bytes(data), len(data))
        assert self.env._lib.retro_unserialize(buf, len(data)), 'unserialize failed'


class _Data:
    def __init__(self, env): self.memory = _Memory(env)


class Env:
    def __init__(self, game):
        if _state.get('loaded') not in (None, game):
            raise RuntimeError('one game per process with this stand-in; start a new process for another ROM')
        self._lib = lib = _load_core(); self.game = game
        if not _state.get('loaded'):
            rom = open(GAMES[game], 'rb').read(); self._rombuf = C.create_string_buffer(rom, len(rom))
            info = _GameInfo(GAMES[game].encode(), C.cast(self._rombuf, C.c_void_p), len(rom), None)
            _state['rombuf'] = self._rombuf
            assert lib.retro_load_game(C.byref(info)), 'core refused the ROM'
            _state['loaded'] = game
        ptr = lib.retro_get_memory_data(2); size = lib.retro_get_memory_size(2)     # RETRO_MEMORY_SYSTEM_RAM
        assert size == 0x10000, f'unexpected work RAM size {size}'
        self._ram = (C.c_uint8 * size).from_address(ptr)
        self.em = _Em(self); self.data = _Data(self); self.unwrapped = self
    def reset(self):
        self._lib.retro_reset(); return None, {}
    def step(self, action):
        b = _state['buttons']
        for i in range(12): b[i] = 1 if action[i] else 0
        self._lib.retro_run(); return None, 0.0, False, False, {}
    def get_ram(self):
        return np.frombuffer(bytes(self._ram), dtype=np.uint8).copy()
    def screen(self):
        data, w, h, pitch = _state['frame']
        a = np.frombuffer(data, np.uint16).reshape(h, pitch // 2)[:, :w] if _state['fmt'] == 2 else None
        if a is None: raise NotImplementedError(f"pixel format {_state['fmt']}")
        r = ((a >> 11) & 31) << 3; g = ((a >> 5) & 63) << 2; bl = (a & 31) << 3
        return np.dstack([r, g, bl]).astype(np.uint8)
    def close(self): pass


def make(game='BuckRogersCountdownToDoomsday-Genesis-v0', render_mode=None, **kw):
    return Env(game)
