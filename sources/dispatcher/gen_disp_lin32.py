#===============================================================================
# Copyright 2017-2020 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#===============================================================================

#
# Intel(R) Integrated Performance Primitives (Intel(R) IPP) Cryptography
#

import re
import sys
import os
import hashlib
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-i', '--header', action='store', required=True, help='Intel(R) IPP Crypto dispatcher will be generated for fucntions in Header')
parser.add_argument('-o', '--out-directory', action='store', required=True, help='Output folder for generated files')
parser.add_argument('-l', '--cpu-list', action='store', required=True, help='Actual CPU list: semicolon separated string')
parser.add_argument('-c', '--compiler', action='store', required=True, help='Compiler')
args = parser.parse_args()
Header = args.header
OutDir = args.out_directory
cpulist = args.cpu_list.split(';')
compiler = args.compiler

headerID= False      ## Header ID define to avoid multiple include like: #if !defined( __IPPCP_H__ )

from gen_disp_common import readNextFunction

HDR= open( Header, 'r' )
h= HDR.readlines()
HDR.close()


## keep filename only
(incdir, Header)= os.path.split(Header)

## original header name to declare external functions as internal for dispatcher
OrgH= Header

isFunctionFound = True
curLine = 0
FunName = ""
FunArg = ""

if(compiler == "GNU" or compiler == "Clang"):
      while (isFunctionFound == True):

            result = readNextFunction(h, curLine, headerID)

            curLine         = result['curLine']
            FunName         = result['FunName']
            FunArg          = result['FunArg']
            isFunctionFound = result['success']

            if (isFunctionFound == True):

                  ##################################################
                  ## create dispatcher files ASM
                  ##################################################
                  ASMDISP= open( os.sep.join([OutDir, "jmp_" + FunName+"_" + hashlib.sha512(FunName.encode('utf-8')).hexdigest()[:8] +".asm"]), 'w' )

                  for cpu in cpulist:
                      ASMDISP.write("extern "+cpu+"_"+FunName+":function\n")

                  ASMDISP.write("extern ippcpJumpIndexForMergedLibs\n")
                  ASMDISP.write("extern ippcpInit:function\n\n")

                  ASMDISP.write("""
segment .data
align 4
dd  .Lin_{FunName}
.Larraddr_{FunName}:
""".format(FunName=FunName))

                  for cpu in cpulist:
                        ASMDISP.write("    dd "+cpu+"_"+FunName+"\n")

                  ASMDISP.write("""

segment .text
extern _GLOBAL_OFFSET_TABLE_
global {FunName}:function ({FunName}.LEnd{FunName} - {FunName})
.Lin_{FunName}:
    {endbr32}
    push ebx
    mov ebx, eax
    call  ippcpInit wrt ..plt
    pop ebx
    align 16
{FunName}:
    {endbr32}
    call .L1
.L1:
      pop   eax
      add   eax, _GLOBAL_OFFSET_TABLE_ + $$ - .L1 wrt ..gotpc
      mov   edx, [eax + ippcpJumpIndexForMergedLibs wrt ..got]
      mov   edx, [edx]
      jmp   dword [eax + edx*4 + .Larraddr_{FunName} wrt ..gotoff]
.LEnd{FunName}:
""".format(FunName=FunName, endbr32='db 0xf3, 0x0f, 0x1e, 0xfb'))
            ASMDISP.close()
else:

      while (isFunctionFound == True):

            result = readNextFunction(h, curLine, headerID)

            curLine         = result['curLine']
            FunName         = result['FunName']
            FunArg          = result['FunArg']
            isFunctionFound = result['success']

            if (isFunctionFound == True):

                  ##################################################
                  ## create dispatcher files: C file with inline asm
                  ##################################################
                  DISP= open( os.sep.join([OutDir, "jmp_"+FunName+"_" + hashlib.sha512(FunName.encode('utf-8')).hexdigest()[:8] + ".c"]), 'w' )

                  DISP.write("""#include "ippcpdefs.h"\n\n""")

                  DISP.write("typedef void (*IPP_PROC)(void);\n\n")
                  DISP.write("extern int ippcpJumpIndexForMergedLibs;\n")
                  DISP.write("extern IPP_STDCALL ippcpInit();\n\n")

                  DISP.write("extern IppStatus IPP_STDCALL in_"+FunName+FunArg+";\n")

                  for cpu in cpulist:
                        DISP.write("extern IppStatus IPP_STDCALL "+cpu+"_"+FunName+FunArg+";\n")

                  DISP.write("""
__asm( "  .data");
__asm( "    .align 4");
__asm( "arraddr:");
__asm( "    .long	in_{FunName}");""".format(FunName=FunName))
                  size = 4
                  for cpu in cpulist:
                        size = size + 4
                        DISP.write("""\n__asm( "    .long	{cpu}_{FunName}");""".format(FunName=FunName, cpu=cpu))

                  DISP.write("""
__asm( "    .type	arraddr,@object");
__asm( "    .size	arraddr,{size}");
__asm( "  .data");\n""".format(size=size))

                  DISP.write("""
#undef  IPPAPI
#define IPPAPI(type,name,arg) __declspec(naked) void IPP_STDCALL name arg
__declspec(naked) IPP_PROC {FunName}{FunArg}
{{
    __asm( ".L0: call .L1");
    __asm( ".L1: pop %eax");
    __asm( "add $_GLOBAL_OFFSET_TABLE_ - .L1, %eax" );
    __asm( "movd ippcpJumpIndexForMergedLibs@GOT(%eax), %xmm0" );
    __asm( "movd %xmm0, %edx" );
    __asm( "mov (%edx), %edx" );
    __asm( "jmp *(arraddr@GOTOFF+4)(%eax,%edx,4)" );
    __asm( ".global in_{FunName}" );
    __asm( "in_{FunName}:" );
    {endbr32}
    __asm( "push %ebx" );
    __asm( "mov %eax, %ebx" );
    __asm( "call ippcpInit@PLT" );
    __asm( "pop %ebx" );
    __asm( "jmp .L0" );
}};
""".format(FunName=FunName, FunArg=FunArg, endbr32='__asm( ".byte 0xf3, 0x0f, 0x1e, 0xfb" );'))

      DISP.close()

