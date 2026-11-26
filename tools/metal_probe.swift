// WhateverXe Enhanced: user-space Metal smoke test. No kernel writes.
import Foundation
import Metal
import Dispatch
import Darwin

// Timings measure host submission-to-completion latency, not frame rate.
struct Timing {
    let hostMs: Double
    let gpuMs: Double?
}
func summarize(_ values: [Double]) -> (min: Double, median: Double, p95: Double, max: Double) {
    precondition(!values.isEmpty)
    let sorted = values.sorted()
    let n = sorted.count
    let median = (sorted[(n - 1) / 2] + sorted[n / 2]) / 2
    let p95 = sorted[(95 * n + 99) / 100 - 1]
    return (sorted[0], median, p95, sorted[n - 1])
}
func report(_ stage: String, _ id: String, _ samples: [Timing]) {
    func line(_ metric: String, _ values: [Double]) {
        guard !values.isEmpty else {
            print("TIMING registry-id=0x\(id) stage=\(stage) metric=\(metric) unavailable")
            return
        }
        let s = summarize(values)
        print("TIMING registry-id=0x\(id) stage=\(stage) metric=\(metric) samples=\(values.count) " +
              String(format: "min-ms=%.3f median-ms=%.3f p95-ms=%.3f max-ms=%.3f",
                     s.min, s.median, s.p95, s.max))
    }
    line("host-submit", samples.map { $0.hostMs })
    line("gpu", samples.compactMap { $0.gpuMs })
}
func completedTiming(_ command: MTLCommandBuffer, _ timeoutMessage: String) throws -> Timing {
    let done = DispatchSemaphore(value: 0)
    command.addCompletedHandler { _ in done.signal() }
    let start = DispatchTime.now().uptimeNanoseconds
    command.commit()
    guard done.wait(timeout: .now() + .seconds(15)) == .success else {
        throw NSError(domain: "WhateverXeMetalProbe", code: 1,
                      userInfo: [NSLocalizedDescriptionKey: timeoutMessage])
    }
    let end = DispatchTime.now().uptimeNanoseconds
    guard command.status == .completed else {
        throw command.error ?? NSError(domain: "WhateverXeMetalProbe", code: 2,
                      userInfo: [NSLocalizedDescriptionKey: "command-failed"])
    }
    let gpuStart = command.gpuStartTime, gpuEnd = command.gpuEndTime
    let gpu: Double? = gpuStart.isFinite && gpuEnd.isFinite && gpuStart > 0 && gpuEnd > gpuStart
        ? (gpuEnd - gpuStart) * 1000 : nil
    return Timing(hostMs: Double(end - start) / 1_000_000, gpuMs: gpu)
}

let source = """
#include <metal_stdlib>
using namespace metal;
kernel void wex_probe(device uint *output [[buffer(0)]],
                      constant uint &seed [[buffer(1)]],
                      uint index [[thread_position_in_grid]]) {
    if (index < 256u) output[index] = (index * 17u) ^ 0x5a5au ^ seed;
}
"""

func probe(_ device: MTLDevice, iterations: Int) throws -> [Timing] {
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
                                         options: .storageModeShared) else {
        throw failure("buffer-unavailable")
    }
    let values = output.contents().bindMemory(to: UInt32.self, capacity: count)
    var samples = [Timing]()
    for iteration in 0..<iterations {
        guard let command = queue.makeCommandBuffer(),
              let encoder = command.makeComputeCommandEncoder() else {
            throw failure("encoder-unavailable iteration=\(iteration + 1)")
        }
        var seed = UInt32(iteration)
        for index in 0..<count { values[index] = UInt32.max }
        encoder.setComputePipelineState(pipeline)
        encoder.setBuffer(output, offset: 0, index: 0)
        encoder.setBytes(&seed, length: MemoryLayout<UInt32>.size, index: 1)
        let width = max(1, min(pipeline.threadExecutionWidth, pipeline.maxTotalThreadsPerThreadgroup, count))
        // Use uniform groups even on devices without nonuniform dispatch support.
        encoder.dispatchThreadgroups(MTLSize(width: (count + width - 1) / width, height: 1, depth: 1),
                                     threadsPerThreadgroup: MTLSize(width: width, height: 1, depth: 1))
        encoder.endEncoding()
        let timing = try completedTiming(command, "compute-completion-timeout iteration=\(iteration + 1)")
        for index in 0..<count {
            let expected = (UInt32(index) * 17) ^ 0x5a5a ^ seed
            guard values[index] == expected else {
                throw failure("output-mismatch-at-index-\(index) iteration=\(iteration + 1)")
            }
        }
        samples.append(timing)
    }
    return samples
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
fragment float4 wex_fragment(float4 position [[position]], constant uint &seed [[buffer(0)]]) {
    uint2 pixel = uint2(position.xy);
    return float4(float((pixel.x ^ seed) & 1u), float((pixel.y ^ (seed >> 1)) & 1u), 1.0, 1.0);
}
"""

func probeRender(_ device: MTLDevice, iterations: Int) throws -> [Timing] {
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
          let queue = device.makeCommandQueue() else {
        throw failure("render-resource-allocation")
    }
    let pixels = readback.contents().bindMemory(to: UInt8.self, capacity: rowBytes * height)
    var samples = [Timing]()
    for iteration in 0..<iterations {
        guard let command = queue.makeCommandBuffer() else {
            throw failure("render-command-buffer-unavailable iteration=\(iteration + 1)")
        }
        var seed = UInt32(iteration)
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
        render.setFragmentBytes(&seed, length: MemoryLayout<UInt32>.size, index: 0)
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
        let timing = try completedTiming(command, "render-completion-timeout iteration=\(iteration + 1)")
        for y in 0..<height {
            for x in 0..<width {
                let offset = y * rowBytes + x * 4
                guard pixels[offset] == UInt8(((x ^ Int(seed)) & 1) * 255),
                      pixels[offset + 1] == UInt8(((y ^ Int(seed >> 1)) & 1) * 255),
                      pixels[offset + 2] == 255, pixels[offset + 3] == 255 else {
                    throw failure("render-pixel-mismatch-at-\(x),\(y) iteration=\(iteration + 1)")
                }
            }
        }
        samples.append(timing)
    }
    return samples
}

// Advanced diagnostics are opt-in: preserve the default E4 workload and CLI.
// Buffer-backed textures test alias visibility across CPU writes, GPU reads
// and command completion. Do not silently replace a rejected linear texture.
let linearSource = """
#include <metal_stdlib>
using namespace metal;
kernel void wex_linear(texture2d<uint, access::read> input [[texture(0)]],
                       device uint *output [[buffer(0)]],
                       uint i [[thread_position_in_grid]]) {
    if (i < 64u) output[i] = input.read(uint2(i % 8u, i / 8u)).r;
}
"""

func linearValue(_ index: Int, _ seed: UInt32) -> UInt32 {
    (UInt32(index) &* 0x10203) ^ seed ^ 0x12345678
}
func advancedFailure(_ message: String) -> NSError {
    NSError(domain: "WhateverXeAdvancedMetalProbe", code: 1,
            userInfo: [NSLocalizedDescriptionKey: message])
}
func probeLinearTexture(_ device: MTLDevice, iterations: Int) throws -> [Timing] {
    let width = 8, height = 8, count = 64
    let format = MTLPixelFormat.r32Uint
    let alignment = device.minimumLinearTextureAlignment(for: format)
    guard alignment > 0 && alignment <= 65536 else {
        throw advancedFailure("linear-texture-alignment-unavailable")
    }
    let rowBytes = ((width * 4 + alignment - 1) / alignment) * alignment
    let desc = MTLTextureDescriptor.texture2DDescriptor(
        pixelFormat: format, width: width, height: height, mipmapped: false)
    desc.storageMode = .shared
    desc.usage = .shaderRead
    guard let backing = device.makeBuffer(length: rowBytes * height, options: .storageModeShared),
          let texture = backing.makeTexture(descriptor: desc, offset: 0, bytesPerRow: rowBytes),
          let output = device.makeBuffer(length: count * 4, options: .storageModeShared),
          let queue = device.makeCommandQueue() else {
        throw advancedFailure("linear-texture-resource-unavailable")
    }
    let library = try device.makeLibrary(source: linearSource, options: nil)
    guard let function = library.makeFunction(name: "wex_linear") else {
        throw advancedFailure("linear-texture-function-unavailable")
    }
    let pipeline = try device.makeComputePipelineState(function: function)
    let values = output.contents().bindMemory(to: UInt32.self, capacity: count)
    var samples = [Timing]()
    for iteration in 0..<iterations {
        let seed = UInt32(iteration)
        for y in 0..<height {
            let row = backing.contents().advanced(by: y * rowBytes)
            for x in 0..<width {
                row.storeBytes(of: linearValue(y * width + x, seed), toByteOffset: x * 4, as: UInt32.self)
            }
        }
        for i in 0..<count { values[i] = ~linearValue(i, seed) }
        guard let command = queue.makeCommandBuffer(),
              let encoder = command.makeComputeCommandEncoder() else {
            throw advancedFailure("linear-texture-encoder-unavailable")
        }
        encoder.setComputePipelineState(pipeline)
        encoder.setTexture(texture, index: 0)
        encoder.setBuffer(output, offset: 0, index: 0)
        let group = max(1, min(pipeline.threadExecutionWidth, pipeline.maxTotalThreadsPerThreadgroup, count))
        encoder.dispatchThreadgroups(MTLSize(width: (count + group - 1) / group, height: 1, depth: 1),
                                     threadsPerThreadgroup: MTLSize(width: group, height: 1, depth: 1))
        encoder.endEncoding()
        let timing = try completedTiming(command, "linear-texture-timeout iteration=\(iteration + 1)")
        for i in 0..<count {
            guard values[i] == linearValue(i, seed) else {
                throw advancedFailure("linear-texture-mismatch index=\(i) iteration=\(iteration + 1)")
            }
        }
        samples.append(timing)
    }
    return samples
}

// A constant RGBA8 image must survive filtering exactly at every mip level.
// Distinct iteration colors and poisoned readback prevent stale-result passes.
// One upload, mip generation and all copies are ordered on a single blit encoder.
func mipColor(_ iteration: Int) -> [UInt8] {
    [UInt8(truncatingIfNeeded: iteration), UInt8(truncatingIfNeeded: iteration >> 8), 173, 255]
}
func probeMipmaps(_ device: MTLDevice, iterations: Int) throws -> [Timing] {
    let side = 8, rowBytes = 256, levelBytes = 2048, levels = 4
    let desc = MTLTextureDescriptor.texture2DDescriptor(
        pixelFormat: .rgba8Unorm, width: side, height: side, mipmapped: true)
    desc.storageMode = .private
    desc.usage = .shaderRead
    guard let texture = device.makeTexture(descriptor: desc), texture.mipmapLevelCount == levels,
          let upload = device.makeBuffer(length: levelBytes, options: .storageModeShared),
          let readback = device.makeBuffer(length: levelBytes * levels, options: .storageModeShared),
          let queue = device.makeCommandQueue() else {
        throw advancedFailure("mipmap-resource-unavailable")
    }
    let input = upload.contents().bindMemory(to: UInt8.self, capacity: levelBytes)
    let output = readback.contents().bindMemory(to: UInt8.self, capacity: levelBytes * levels)
    var samples = [Timing]()
    for iteration in 0..<iterations {
        let color = mipColor(iteration)
        for y in 0..<side {
            for x in 0..<side {
                for channel in 0..<4 { input[y * rowBytes + x * 4 + channel] = color[channel] }
            }
        }
        for i in 0..<(levelBytes * levels) { output[i] = 0x5c }
        guard let command = queue.makeCommandBuffer(),
              let blit = command.makeBlitCommandEncoder() else {
            throw advancedFailure("mipmap-blit-unavailable")
        }
        let origin = MTLOrigin(x: 0, y: 0, z: 0)
        blit.copy(from: upload, sourceOffset: 0, sourceBytesPerRow: rowBytes,
                  sourceBytesPerImage: levelBytes,
                  sourceSize: MTLSize(width: side, height: side, depth: 1),
                  to: texture, destinationSlice: 0, destinationLevel: 0, destinationOrigin: origin)
        blit.generateMipmaps(for: texture)
        for level in 0..<levels {
            let size = side >> level
            blit.copy(from: texture, sourceSlice: 0, sourceLevel: level,
                      sourceOrigin: origin, sourceSize: MTLSize(width: size, height: size, depth: 1),
                      to: readback, destinationOffset: level * levelBytes,
                      destinationBytesPerRow: rowBytes, destinationBytesPerImage: levelBytes)
        }
        blit.endEncoding()
        let timing = try completedTiming(command, "mipmap-timeout iteration=\(iteration + 1)")
        for level in 0..<levels {
            let size = side >> level
            for y in 0..<size {
                for x in 0..<size {
                    for channel in 0..<4 {
                        let offset = level * levelBytes + y * rowBytes + x * 4 + channel
                        guard output[offset] == color[channel] else {
                            throw advancedFailure("mipmap-mismatch level=\(level) x=\(x) y=\(y) channel=\(channel) iteration=\(iteration + 1)")
                        }
                    }
                }
            }
        }
        samples.append(timing)
    }
    return samples
}

let args = Array(CommandLine.arguments.dropFirst())
if args == ["--self-test"] {
    let a = summarize([3, 1, 2, 4])
    let b = summarize([7])
    let c = summarize((1...100).map { Double($0) })
    guard a.min == 1 && a.median == 2.5 && a.p95 == 4 && a.max == 4 &&
          b.min == 7 && b.median == 7 && b.p95 == 7 && b.max == 7 &&
          c.median == 50.5 && c.p95 == 95 else { exit(1) }
    guard linearValue(0, 0) == 0x12345678,
          linearValue(1, 0) == 0x1235547b,
          linearValue(0, 1) == 0x12345679,
          mipColor(0) == [0, 0, 173, 255],
          mipColor(256) == [0, 1, 173, 255],
          mipColor(999) == [231, 3, 173, 255] else { exit(1) }
    print("PASS host-only timing statistics and advanced expected-value fixtures")
    exit(0)
}
func usage() -> Never {
    fputs("Usage: metal_probe [--registry-id decimal-or-0xhex] [--iterations 1...1000] [--suite standard|advanced]\n", stderr)
    exit(2)
}
var requested: UInt64? = nil
var iterations = 1
var advanced = false
var seen = Set<String>()
var index = 0
while index < args.count {
    let option = args[index]
    guard index + 1 < args.count, seen.insert(option).inserted else { usage() }
    let value = args[index + 1]
    switch option {
    case "--registry-id":
        requested = value.hasPrefix("0x") ? UInt64(value.dropFirst(2), radix: 16) : UInt64(value)
        guard requested != nil else { usage() }
    case "--iterations":
        guard let n = Int(value), (1...1000).contains(n) else { usage() }
        iterations = n
    case "--suite":
        guard value == "standard" || value == "advanced" else { usage() }
        advanced = value == "advanced"
    default: usage()
    }
    index += 2
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
        let samples = try probe(device, iterations: iterations)
        print("PASS registry-id=0x\(id) compute-output-verified iterations=\(iterations)")
        report("compute", id, samples)
    } catch {
        failures += 1
        print("FAIL registry-id=0x\(id) stage=compute \(error.localizedDescription)")
        print("SKIP registry-id=0x\(id) stage=render after-compute-failure")
        continue
    }
    do {
        let samples = try probeRender(device, iterations: iterations)
        print("PASS registry-id=0x\(id) render-pixels-verified iterations=\(iterations)")
        report("render", id, samples)
    } catch {
        failures += 1
        print("FAIL registry-id=0x\(id) stage=render \(error.localizedDescription)")
        if advanced { continue }
    }
    if advanced {
        // A timed-out command may still be running: stop this device's suite
        // on a failure rather than enqueue additional advanced GPU work.
        do {
            let samples = try probeLinearTexture(device, iterations: iterations)
            print("PASS registry-id=0x\(id) linear-texture-output-verified iterations=\(iterations)")
            report("linear-texture", id, samples)
            let mipSamples = try probeMipmaps(device, iterations: iterations)
            print("PASS registry-id=0x\(id) mipmap-pixels-verified levels=4 iterations=\(iterations)")
            report("mipmap", id, mipSamples)
        } catch {
            failures += 1
            print("FAIL registry-id=0x\(id) stage=advanced \(error.localizedDescription)")
        }
    }
}
exit(failures == 0 ? 0 : 1)
