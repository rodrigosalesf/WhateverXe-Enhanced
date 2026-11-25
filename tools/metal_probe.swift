// WhateverXe Enhanced: user-space Metal smoke test. No kernel writes.
import Foundation
import Metal
import Dispatch
import Darwin

let source = """
#include <metal_stdlib>
using namespace metal;
kernel void wex_probe(device uint *output [[buffer(0)]],
                      uint index [[thread_position_in_grid]]) {
    if (index < 256u) output[index] = (index * 17u) ^ 0x5a5au;
}
"""

func probe(_ device: MTLDevice) throws {
    func failure(_ message: String) -> NSError {
        NSError(domain: "WhateverXeMetalProbe", code: 1,
                userInfo: [NSLocalizedDescriptionKey: message])
    }
    let count = 256
    guard let queue = device.makeCommandQueue() else { throw failure("command-queue-unavailable") }
    let library = try device.makeLibrary(source: source, options: nil)
    guard let function = library.makeFunction(name: "wex_probe") else { throw failure("function-unavailable") }
    let pipeline = try device.makeComputePipelineState(function: function)
    guard let output = device.makeBuffer(length: count * MemoryLayout<UInt32>.stride,
                                         options: .storageModeShared),
          let command = queue.makeCommandBuffer(),
          let encoder = command.makeComputeCommandEncoder() else {
        throw failure("buffer-or-encoder-unavailable")
    }
    let values = output.contents().bindMemory(to: UInt32.self, capacity: count)
    for index in 0..<count { values[index] = UInt32.max }
    encoder.setComputePipelineState(pipeline)
    encoder.setBuffer(output, offset: 0, index: 0)
    let width = max(1, min(pipeline.threadExecutionWidth, pipeline.maxTotalThreadsPerThreadgroup, count))
    // Use uniform groups even on devices without nonuniform dispatch support.
    encoder.dispatchThreadgroups(MTLSize(width: (count + width - 1) / width, height: 1, depth: 1),
                                 threadsPerThreadgroup: MTLSize(width: width, height: 1, depth: 1))
    encoder.endEncoding()
    let done = DispatchSemaphore(value: 0)
    command.addCompletedHandler { _ in done.signal() }
    command.commit()
    guard done.wait(timeout: .now() + .seconds(15)) == .success else {
        throw failure("command-completion-timeout")
    }
    guard command.status == .completed else {
        throw command.error ?? failure("command-failed")
    }
    for index in 0..<count {
        let expected = (UInt32(index) * 17) ^ 0x5a5a
        guard values[index] == expected else {
            throw failure("output-mismatch-at-index-\(index)")
        }
    }
}

// Exercise the graphics compiler and raster pipeline independently of the
// compute probe. A private render target plus blit also checks GPU readback.
let renderSource = """
#include <metal_stdlib>
using namespace metal;
vertex float4 wex_vertex(uint index [[vertex_id]]) {
    const float2 positions[3] = {float2(-1.0, -1.0), float2(3.0, -1.0), float2(-1.0, 3.0)};
    return float4(positions[index], 0.0, 1.0);
}
fragment float4 wex_fragment(float4 position [[position]]) {
    uint2 pixel = uint2(position.xy);
    return float4(float(pixel.x & 1u), float(pixel.y & 1u), 1.0, 1.0);
}
"""

func probeRender(_ device: MTLDevice) throws {
    func failure(_ message: String) -> NSError {
        NSError(domain: "WhateverXeMetalRenderProbe", code: 1,
                userInfo: [NSLocalizedDescriptionKey: message])
    }
    let width = 16, height = 16, rowBytes = 256
    let library: MTLLibrary
    do { library = try device.makeLibrary(source: renderSource, options: nil) }
    catch { throw failure("render-shader-compilation: \(error.localizedDescription)") }
    guard let vertex = library.makeFunction(name: "wex_vertex"),
          let fragment = library.makeFunction(name: "wex_fragment") else {
        throw failure("render-functions-unavailable")
    }
    let descriptor = MTLRenderPipelineDescriptor()
    descriptor.vertexFunction = vertex
    descriptor.fragmentFunction = fragment
    descriptor.colorAttachments[0].pixelFormat = .rgba8Unorm
    let pipeline: MTLRenderPipelineState
    do { pipeline = try device.makeRenderPipelineState(descriptor: descriptor) }
    catch { throw failure("render-pipeline-compilation: \(error.localizedDescription)") }

    let textureDescriptor = MTLTextureDescriptor.texture2DDescriptor(
        pixelFormat: .rgba8Unorm, width: width, height: height, mipmapped: false)
    textureDescriptor.storageMode = .private
    textureDescriptor.usage = .renderTarget
    guard let target = device.makeTexture(descriptor: textureDescriptor),
          let readback = device.makeBuffer(length: rowBytes * height, options: .storageModeShared),
          let queue = device.makeCommandQueue(),
          let command = queue.makeCommandBuffer() else {
        throw failure("render-resource-allocation")
    }
    let pixels = readback.contents().bindMemory(to: UInt8.self, capacity: rowBytes * height)
    for offset in 0..<(rowBytes * height) { pixels[offset] = 0x7b }
    let pass = MTLRenderPassDescriptor()
    pass.colorAttachments[0].texture = target
    pass.colorAttachments[0].loadAction = .clear
    pass.colorAttachments[0].clearColor = MTLClearColorMake(0, 0, 0, 0)
    pass.colorAttachments[0].storeAction = .store
    guard let render = command.makeRenderCommandEncoder(descriptor: pass) else {
        throw failure("render-encoder-unavailable")
    }
    render.setRenderPipelineState(pipeline)
    render.setCullMode(.none)
    render.setViewport(MTLViewport(originX: 0, originY: 0, width: Double(width),
                                   height: Double(height), znear: 0, zfar: 1))
    render.drawPrimitives(type: .triangle, vertexStart: 0, vertexCount: 3)
    render.endEncoding()
    guard let blit = command.makeBlitCommandEncoder() else {
        throw failure("blit-encoder-unavailable")
    }
    blit.copy(from: target, sourceSlice: 0, sourceLevel: 0,
              sourceOrigin: MTLOrigin(x: 0, y: 0, z: 0),
              sourceSize: MTLSize(width: width, height: height, depth: 1),
              to: readback, destinationOffset: 0, destinationBytesPerRow: rowBytes,
              destinationBytesPerImage: rowBytes * height)
    blit.endEncoding()
    let done = DispatchSemaphore(value: 0)
    command.addCompletedHandler { _ in done.signal() }
    command.commit()
    guard done.wait(timeout: .now() + .seconds(15)) == .success else {
        throw failure("render-completion-timeout")
    }
    guard command.status == .completed else {
        throw command.error ?? failure("render-command-failed")
    }
    for y in 0..<height {
        for x in 0..<width {
            let offset = y * rowBytes + x * 4
            guard pixels[offset] == UInt8((x & 1) * 255),
                  pixels[offset + 1] == UInt8((y & 1) * 255),
                  pixels[offset + 2] == 255, pixels[offset + 3] == 255 else {
                throw failure("render-pixel-mismatch-at-\(x),\(y)")
            }
        }
    }
}

let args = Array(CommandLine.arguments.dropFirst())
var requested: UInt64? = nil
if !args.isEmpty {
    guard args.count == 2, args[0] == "--registry-id" else {
        fputs("Usage: metal_probe [--registry-id decimal-or-0xhex]\n", stderr)
        exit(2)
    }
    let value = args[1]
    requested = value.hasPrefix("0x") ? UInt64(value.dropFirst(2), radix: 16) : UInt64(value)
    guard requested != nil else { fputs("Invalid registry ID\n", stderr); exit(2) }
}
let devices = MTLCopyAllDevices()
for device in devices {
    print("DEVICE registry-id=0x\(String(device.registryID, radix: 16)) name=\(device.name) low-power=\(device.isLowPower) unified-memory=\(device.hasUnifiedMemory)")
}
let selected = devices.filter { requested == nil || $0.registryID == requested }
guard !selected.isEmpty else {
    print("FAIL no matching Metal device")
    exit(1)
}
var failures = 0
for device in selected {
    let id = String(device.registryID, radix: 16)
    do {
        try probe(device)
        print("PASS registry-id=0x\(id) compute-output-verified")
    } catch {
        failures += 1
        print("FAIL registry-id=0x\(id) stage=compute \(error.localizedDescription)")
        print("SKIP registry-id=0x\(id) stage=render after-compute-failure")
        continue
    }
    do {
        try probeRender(device)
        print("PASS registry-id=0x\(id) render-pixels-verified")
    } catch {
        failures += 1
        print("FAIL registry-id=0x\(id) stage=render \(error.localizedDescription)")
    }
}
exit(failures == 0 ? 0 : 1)
