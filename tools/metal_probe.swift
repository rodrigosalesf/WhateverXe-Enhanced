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
        print("FAIL registry-id=0x\(id) \(error.localizedDescription)")
    }
}
exit(failures == 0 ? 0 : 1)
