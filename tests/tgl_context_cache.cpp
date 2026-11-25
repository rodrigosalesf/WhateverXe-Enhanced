#include "kern_tgl_context_cache.hpp"
#include <cassert>
#include <array>
#include <sys/mman.h>
#include <unistd.h>
int main() {
 std::array<uint8_t,81920> image{},before{};std::array<uint8_t,8192> page{};
 const uint64_t gpu=0x402b3000;const uint32_t fields[]={0x21C0,uint32_t(gpu|5),0x21C4,0,0x21C8,0};
 memcpy(image.data()+0x1048,fields,sizeof(fields));before=image;
 assert(TGLContextCache::install(image.data(),image.size(),gpu));
 for(size_t i=0;i<image.size();++i)if((i<0x1054||i>=0x1058)&&(i<0x105C||i>=0x1060))assert(image[i]==before[i]);
 auto installed=image;assert(TGLContextCache::install(image.data(),image.size(),gpu));assert(image==installed);
 // Verify idempotence with an actual read-only mapping: even an identical
 // store is a fault. Test the two accepted partially populated states too.
 const size_t bytes=0x1060;
 auto mapped=mmap(nullptr,bytes,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
 assert(mapped!=MAP_FAILED);memcpy(mapped,installed.data(),bytes);
 assert(mprotect(mapped,bytes,PROT_READ)==0);
 assert(TGLContextCache::install(mapped,bytes,gpu));
 assert(!memcmp(mapped,installed.data(),bytes));
 assert(munmap(mapped,bytes)==0);
 for(unsigned field:{3U,5U}) {
  image=installed;uint32_t zero=0;memcpy(image.data()+0x1048+field*4,&zero,4);
  assert(TGLContextCache::install(image.data(),image.size(),gpu) && image==installed);
 }
 // Verify the exact minimum image extent and highest permitted GGTT base,
 // including unaligned CPU storage (all fields are copied as bytes).
 std::array<uint8_t,0x1062> edge{};edge.front()=0x5a;edge.back()=0xa5;
 const uint64_t maxGPU=0xFFFFE000ULL;
 const uint32_t maxFields[]={0x21C0,uint32_t(maxGPU|5),0x21C4,0,0x21C8,0};
 memcpy(edge.data()+1+0x1048,maxFields,sizeof(maxFields));
 assert(TGLContextCache::install(edge.data()+1,bytes,maxGPU));
 uint32_t maxPointer=0;memcpy(&maxPointer,edge.data()+1+0x1054,4);
 assert(maxPointer==0xFFFFF001U && edge.front()==0x5a && edge.back()==0xa5);
 assert(!TGLContextCache::install(nullptr,bytes,gpu));
 for(unsigned field:{0U,1U,2U,3U,4U,5U}) {
  image=before;uint32_t bad=0x12345678;memcpy(image.data()+0x1048+field*4,&bad,4);auto copy=image;
  assert(!TGLContextCache::install(image.data(),image.size(),gpu));assert(image==copy);
 }
 for(uint64_t bad:{0ULL,0x402b3001ULL,0xFFFFF000ULL,0x100000000ULL})assert(!TGLContextCache::install(before.data(),before.size(),bad));
 assert(!TGLContextCache::install(before.data(),0x105F,gpu));
 page.fill(0xA5);TGLContextCache::batch(page.data());uint32_t words[16];memcpy(words,page.data()+4096,64);
 assert(words[0]==0x11000001 && words[1]==0x20D8 && words[2]==0x00400040);
 for(unsigned i=3;i<16;++i)assert(!words[i]);
 for(unsigned i=0;i<8192;++i)if(i<4096||i>=4160)assert(page[i]==0xA5);
 for(uint32_t old=0;old<65536;++old)assert(((old&~(words[2]>>16))|(words[2]&0xffff))==(old|0x40));
}
