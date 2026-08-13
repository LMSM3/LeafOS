#include "providers/host_capacity.hpp"

#include <cstdlib>
#include <thread>

#if defined(_WIN32)
#include <windows.h>
#elif defined(__APPLE__)
#include <sys/sysctl.h>
#include <sys/types.h>
#include <unistd.h>
#else
#include <unistd.h>
#endif

namespace leafos::providers {

static double physical_ram_gib() {
	double bytes = 0.0;
#if defined(_WIN32)
	MEMORYSTATUSEX ms;
	ms.dwLength = sizeof(ms);
	if (GlobalMemoryStatusEx(&ms)) {
		bytes = static_cast<double>(ms.ullTotalPhys);
	}
#elif defined(__APPLE__)
	int64_t ram;
	size_t len = sizeof(ram);
	if (sysctlbyname("hw.memsize", &ram, &len, nullptr, 0) == 0) {
		bytes = static_cast<double>(ram);
	}
#elif defined(_SC_PHYS_PAGES)
	long pages = sysconf(_SC_PHYS_PAGES);
	long page_size = sysconf(_SC_PAGE_SIZE);
	if (pages > 0 && page_size > 0) bytes = static_cast<double>(pages) * static_cast<double>(page_size);
#endif
	return bytes / (1024.0 * 1024.0 * 1024.0);
}

static uint32_t logical_cpus() {
	return static_cast<uint32_t>(std::max(1u, std::thread::hardware_concurrency()));
}

HostCapacity detect_host_capacity() {
	HostCapacity hc;
	hc.available_ram_gib = physical_ram_gib();
	hc.available_vram_gib = -1.0; // not detected in iteration A
	hc.reserved_memory_gib = 2.0;
	hc.logical_cpus = logical_cpus();
	return hc;
}

} // namespace leafos::providers
