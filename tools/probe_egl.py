#!/usr/bin/env python3
"""Small Linux/WSLg EGL pbuffer smoke measurement; not a Gazebo benchmark."""
import ctypes as C
import json
import time


def probe():
    egl = C.CDLL('libEGL.so.1')
    try:
        gl = C.CDLL('libGLESv2.so.2')
        api, renderable = 0x30A0, 4
        context_attributes = (C.c_int * 3)(0x3098, 2, 0x3038)
    except OSError:
        gl = C.CDLL('libGL.so.1')
        api, renderable = 0x30A2, 8
        context_attributes = (C.c_int * 1)(0x3038)
    egl.eglGetDisplay.argtypes = [C.c_void_p]
    egl.eglGetDisplay.restype = C.c_void_p
    egl.eglInitialize.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
    egl.eglChooseConfig.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_void_p), C.c_int, C.POINTER(C.c_int)]
    egl.eglBindAPI.argtypes = [C.c_uint]
    egl.eglCreatePbufferSurface.argtypes = [C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
    egl.eglCreatePbufferSurface.restype = C.c_void_p
    egl.eglCreateContext.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.POINTER(C.c_int)]
    egl.eglCreateContext.restype = C.c_void_p
    egl.eglMakeCurrent.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p]
    egl.eglDestroyContext.argtypes = [C.c_void_p, C.c_void_p]
    egl.eglDestroySurface.argtypes = [C.c_void_p, C.c_void_p]
    egl.eglTerminate.argtypes = [C.c_void_p]
    gl.glGetString.argtypes = [C.c_uint]
    gl.glGetString.restype = C.c_char_p
    gl.glClearColor.argtypes = [C.c_float] * 4
    gl.glClear.argtypes = [C.c_uint]
    gl.glClear.restype = None
    gl.glClearColor.restype = None
    gl.glFinish.restype = None
    display = egl.eglGetDisplay(None)
    major, minor = C.c_int(), C.c_int()
    if not egl.eglInitialize(display, C.byref(major), C.byref(minor)):
        raise RuntimeError('EGL display initialization failed')
    surface = context = None
    try:
        attributes = (C.c_int * 13)(0x3033, 1, 0x3040, renderable, 0x3024, 8, 0x3023, 8, 0x3022, 8, 0x3021, 8, 0x3038)
        configuration, number = C.c_void_p(), C.c_int()
        if not egl.eglChooseConfig(display, attributes, C.byref(configuration), 1, C.byref(number)) or not number.value:
            raise RuntimeError('No pbuffer EGL configuration')
        egl.eglBindAPI(api)
        surface = egl.eglCreatePbufferSurface(display, configuration, (C.c_int * 5)(0x3057, 256, 0x3056, 256, 0x3038))
        context = egl.eglCreateContext(display, configuration, None, context_attributes)
        if not surface or not context or not egl.eglMakeCurrent(display, surface, surface, context):
            raise RuntimeError('EGL context creation or activation failed')
        info = {key: (gl.glGetString(token) or b'').decode() for key, token in
                [('vendor',0x1F00),('renderer',0x1F01),('version',0x1F02)]}
        gl.glClearColor(0.2,0.3,0.4,1)
        started = time.perf_counter()
        for _ in range(200):
            gl.glClear(0x4000)
            gl.glFinish()
        info.update({'kind': 'EGL_256x256_clear_finish_smoke', 'iterations': 200,
                     'elapsed_seconds': time.perf_counter()-started,
                     'limitation': 'Offscreen clear only; does not measure scene rendering, sensors, physics or Gazebo FPS.'})
        return info
    finally:
        egl.eglMakeCurrent(display, None, None, None)
        if context:
            egl.eglDestroyContext(display, context)
        if surface:
            egl.eglDestroySurface(display, surface)
        egl.eglTerminate(display)


if __name__ == '__main__':
    try:
        print(json.dumps(probe()))
    except (OSError, RuntimeError) as exc:
        print(json.dumps({'kind':'EGL_probe_failed','error':str(exc)}))
        raise SystemExit(1)
