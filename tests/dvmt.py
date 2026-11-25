#!/usr/bin/env python3
"""Exercise the extracted DVMT admission/calculation against BIOS GMS fixtures."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1]
s=(r/'WhateverXe/kern_dvmt.cpp').read_text();body=s[s.index('void DVMTCalcFix::processKernel'):s.index('void DVMTCalcFix::processFramebufferKext')]
code=r'''
#include <cstdint>
#include <cassert>
#include <cstdio>
#define SYSLOG(...)
#define DBGLOG(...)
bool optin=true;
bool checkKernelArgument(const char *){return optin;}
bool property=false,published=true;
struct GPU {void *getProperty(const char *){return property?this:nullptr;}};
struct KernelPatcher {};struct DeviceInfo {GPU *videoBuiltin;};
namespace WIOKit {uint32_t ggc;constexpr int kIOPCIConfigGraphicsControl=0x50;bool awaitPublishing(GPU *){return published;}uint32_t readPCIConfigValue(GPU *,int,int,int){return ggc;}}
class DVMTCalcFix {public:bool applied=false,enabled=false,available=true;uint32_t dvmt=0;void processKernel(KernelPatcher &,DeviceInfo *);};
'''+body+r'''
int main(){GPU gpu;DeviceInfo info{&gpu};KernelPatcher p;
struct Case{unsigned gms,mb;bool patch;};
for(auto c:{Case{1,32,false},Case{2,64,false},Case{3,96,false},Case{15,480,false},Case{0x20,1024,true},Case{0x30,1536,true},Case{0x40,2048,true},Case{0xf0,4,true},Case{0xfe,60,true}}){
 DVMTCalcFix d;WIOKit::ggc=c.gms<<8;d.processKernel(p,&info);assert(d.dvmt==c.mb*1024*1024);assert(d.enabled==c.patch);assert(!d.applied);
}
// Reuse the same object so a rejected read cannot retain previously valid DVMT.
DVMTCalcFix d;
for(unsigned invalid:{0x1000U,0x1100U,0x2100U,0x4100U,0xef00U,0xff00U,0xffffU,0xffffffffU}){
 WIOKit::ggc=0xfe00;d.processKernel(p,&info);assert(d.enabled&&d.dvmt==60*1024*1024);
 WIOKit::ggc=invalid;d.processKernel(p,&info);assert(!d.enabled&&!d.applied&&d.dvmt==0);
}
WIOKit::ggc=0xfe00;d.processKernel(p,&info);assert(d.enabled);
optin=false;d.processKernel(p,&info);assert(!d.enabled&&!d.applied&&d.dvmt==0);
property=true;d.processKernel(p,&info);assert(d.enabled&&d.dvmt==60*1024*1024);
published=false;d.processKernel(p,&info);assert(!d.enabled&&!d.applied&&d.dvmt==0);
published=true;d.available=false;d.processKernel(p,&info);assert(!d.enabled&&!d.applied&&d.dvmt==0);
d.available=true;d.processKernel(p,&info);assert(d.enabled);d.processKernel(p,nullptr);assert(!d.enabled&&!d.applied&&d.dvmt==0);
DeviceInfo noGPU{nullptr};d.processKernel(p,&noGPU);assert(!d.enabled&&!d.applied&&d.dvmt==0);
puts("PASS DVMT: normal 32/64/96/480 MiB stays unpatched; large/special GMS values decode; opt-out, reserved values, invalid reads and missing devices rejected");}
'''
code='#include <initializer_list>\n'+code
with tempfile.TemporaryDirectory(prefix='whxe-dvmt-') as d:
 p=Path(d);(p/'check.cpp').write_text(code)
 subprocess.run(['clang++','-std=c++17','-fsanitize=address,undefined',str(p/'check.cpp'),'-o',str(p/'check')],check=True)
 subprocess.run([str(p/'check')],check=True)
