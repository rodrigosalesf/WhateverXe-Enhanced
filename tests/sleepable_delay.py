#!/usr/bin/env python3
"""Exercise real delay adapters with modeled kernel wait primitives."""
from pathlib import Path
import re, subprocess, tempfile
root = Path(__file__).resolve().parents[1]
source = (root/'WhateverXe/kern_xe.cpp').read_text()
# Identify the specific production adapters by their enclosing entry.
anchors = ['struct Display13FBClockIO {', 'void XE::wrapAlderLakeNDisableDisplay(', 'Display13WM::Latch XE::adlnVerifyWMLatch(']
code = '''#include "kern_sleepable_delay.hpp"
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <vector>
uint64_t elapsed=0;
unsigned sleeps=0, busy=0;
void IOSleep(unsigned n){assert(n);++sleeps;elapsed+=uint64_t(n)*1000;}
void IODelay(unsigned n){assert(n && n<1000);++busy;elapsed+=n;}
'''
for i, anchor in enumerate(anchors):
    start = source.index(anchor)
    method = re.search(r'void delayUs\(unsigned us\)[^\n]+',source[start:]).group()
    code += f'struct Adapter{i} {{ {method} }};\n'
code += '''template<class Adapter> void run(){
 Adapter io;
 for(unsigned us : {0U,1U,10U,999U,1000U,1001U,1500U,2000U,65535U,UINT32_MAX}){
  elapsed=sleeps=busy=0;io.delayUs(us);
  assert(elapsed==us);
  assert(sleeps==(us>=1000));
  assert(busy==(us%1000!=0));
 }
}
int main(){run<Adapter0>();run<Adapter1>();run<Adapter2>();puts("PASS three production sleepable adapters");}
'''
with tempfile.TemporaryDirectory() as d:
    p=Path(d); (p/'test.cpp').write_text(code)
    subprocess.run(['clang++','-std=c++17','-O1','-g','-fsanitize=address,undefined','-I'+str(root/'WhateverXe'),str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],check=True)
