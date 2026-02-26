/**
 * dof_c_api.cpp
 *
 * Thin C bridge over the libdof C++ API.
 * Compile into libdof_python.so with build_wrapper.sh.
 */

#include "dof_c_api.h"

#include "DOF/Config.h"
#include "DOF/DOF.h"

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>

/* ------------------------------------------------------------------ */
/* Internal log forwarding                                             */
/* ------------------------------------------------------------------ */

static DofLogCallbackC g_log_callback = nullptr;

/**
 * Native DOF log callback (receives printf-style format + va_list).
 * We format the message here and forward a plain string to the Python
 * callback so the Python side never needs to touch va_list.
 */
static void internal_log_callback(DOF_LogLevel level,
                                   const char*  format,
                                   va_list      args)
{
    if (!g_log_callback)
        return;

    /* Determine required buffer size */
    va_list args_copy;
    va_copy(args_copy, args);
    int size = vsnprintf(nullptr, 0, format, args_copy);
    va_end(args_copy);

    if (size <= 0) {
        g_log_callback(static_cast<DofLogLevel>(level), "");
        return;
    }

    char* buf = static_cast<char*>(malloc(size + 1));
    if (!buf) return;

    vsnprintf(buf, size + 1, format, args);
    g_log_callback(static_cast<DofLogLevel>(level), buf);
    free(buf);
}


/* ------------------------------------------------------------------ */
/* C API implementation                                                */
/* ------------------------------------------------------------------ */

extern "C" {

void dof_config_set_base_path(const char* path)
{
    DOF::Config::GetInstance()->SetBasePath(path);
}

void dof_config_set_log_level(DofLogLevel level)
{
    DOF::Config::GetInstance()->SetLogLevel(static_cast<DOF_LogLevel>(level));
}

void dof_config_set_log_callback(DofLogCallbackC callback)
{
    g_log_callback = callback;
    if (callback)
        DOF::Config::GetInstance()->SetLogCallback(internal_log_callback);
    else
        DOF::Config::GetInstance()->SetLogCallback(nullptr);
}

void* dof_create(void)
{
    return new DOF::DOF();
}

void dof_destroy(void* dof)
{
    delete static_cast<DOF::DOF*>(dof);
}

void dof_init(void* dof, const char* table_filename, const char* rom_name)
{
    static_cast<DOF::DOF*>(dof)->Init(table_filename, rom_name);
}

void dof_data_receive(void* dof, char type, int number, int value)
{
    static_cast<DOF::DOF*>(dof)->DataReceive(type, number, value);
}

void dof_finish(void* dof)
{
    static_cast<DOF::DOF*>(dof)->Finish();
}

} // extern "C"
