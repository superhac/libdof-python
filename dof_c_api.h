/**
 * dof_c_api.h
 *
 * A plain-C bridge over the libdof C++ API so that Python (ctypes) can
 * load it without dealing with C++ name mangling or va_list ABI quirks.
 *
 * Build with build_wrapper.sh, then load libdof_python.so from Python.
 */

#pragma once

/* Export macro — functions must be explicitly exported on Windows DLLs */
#ifdef _MSC_VER
#  define DOF_PYTHON_API __declspec(dllexport)
#else
#  define DOF_PYTHON_API __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ------------------------------------------------------------------ */
/* Log levels (mirrors DOF_LogLevel in Config.h)                       */
/* ------------------------------------------------------------------ */
typedef enum {
    DOF_LOG_INFO  = 0,
    DOF_LOG_WARN  = 1,
    DOF_LOG_ERROR = 2,
    DOF_LOG_DEBUG = 3
} DofLogLevel;

/**
 * Simple pre-formatted log callback that Python can implement easily.
 * Unlike the native DOF_LogCallback, the message is already formatted
 * (no va_list handling required on the Python side).
 */
typedef void (*DofLogCallbackC)(DofLogLevel level, const char* message);


/* ------------------------------------------------------------------ */
/* Global configuration (wraps DOF::Config singleton)                  */
/* ------------------------------------------------------------------ */

/** Set the base directory where DOF looks for its config files.
 *  On Linux/macOS the default is ~/.vpinball/.
 *  The path should end with a directory separator.
 */
DOF_PYTHON_API void dof_config_set_base_path(const char* path);

/** Set the minimum log level. */
DOF_PYTHON_API void dof_config_set_log_level(DofLogLevel level);

/**
 * Register a Python-friendly log callback.
 * Pass NULL to disable logging.
 * The callback receives an already-formatted string — no printf needed.
 */
DOF_PYTHON_API void dof_config_set_log_callback(DofLogCallbackC callback);


/* ------------------------------------------------------------------ */
/* DOF instance lifecycle                                              */
/* ------------------------------------------------------------------ */

/** Create a new DOF instance. Returns an opaque handle. */
DOF_PYTHON_API void* dof_create(void);

/** Destroy a DOF instance created with dof_create(). */
DOF_PYTHON_API void  dof_destroy(void* dof);


/* ------------------------------------------------------------------ */
/* DOF operations                                                      */
/* ------------------------------------------------------------------ */

/**
 * Initialise DOF for a specific ROM (and optionally a table file).
 * Call once after dof_create() and before any dof_data_receive() calls.
 *
 *   table_filename  – path to the table file, or "" to omit
 *   rom_name        – short ROM name, e.g. "afm", "tna", "ij_l7"
 */
DOF_PYTHON_API void dof_init(void* dof, const char* table_filename, const char* rom_name);

/**
 * Send a game event to DOF.
 *
 *   type   – element type character: 'S' (solenoid), 'L' (lamp),
 *             'W' (switch/GI), 'E' (named element), …
 *   number – element number
 *   value  – 0 = off, 1 = on, or an analogue level (0-255)
 */
DOF_PYTHON_API void dof_data_receive(void* dof, char type, int number, int value);

/**
 * Finish/reset the current DOF session.
 * Call when the table session ends. You can call dof_init() again
 * afterwards to start a new session with the same instance.
 */
DOF_PYTHON_API void dof_finish(void* dof);


#ifdef __cplusplus
}
#endif
