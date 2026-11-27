// Host-testable DIP transaction contract; no hardware backend is provided.
#ifndef KERN_HDMI_DIP_TRANSACTION_HPP
#define KERN_HDMI_DIP_TRANSACTION_HPP

#include "kern_hdmi_audio_payload.hpp"

namespace HDMIAudioPayload {
enum class DipTransmit { disabled, bestEffort, once, unknown };
struct DipState {
    DipImage image {};
    DipTransmit transmit {DipTransmit::unknown};
};
enum class DipTransactionResult {
    rejected, unchanged, applied, rolledBack, rollbackFailed, ownershipLost
};

inline bool sameDipImage(const DipImage &a, const DipImage &b) {
    if (!a.length || a.length > sizeof(a.bytes) || a.length != b.length)
        return false;
    for (size_t i = 0; i < a.length; ++i)
        if (a.bytes[i] != b.bytes[i])
            return false;
    return true;
}

// Backend contract: synchronous, externally serialized, exclusive access to
// the verified connector/pin/packet and generation. owns() is checked around
// every operation; each method must also enforce that ownership before acting.
// read() captures packet bytes and transmit mode without changing either;
// methods must preserve the packet/index cursor. A failed write may have
// partially changed state. No hardware adapter or ABI assumption is supplied.
template <typename Backend>
DipTransactionResult applyDipTransaction(Backend &backend, const DipImage &desired,
                                         DipLayout layout) {
    using Result = DipTransactionResult;
    const auto canonical = buildStereoDipImage(stereoInfoFrame(2), layout, desired.length);
    if (!sameDipImage(desired, canonical))
        return Result::rejected;
    if (!backend.owns())
        return Result::ownershipLost;

    DipState previous {};
    const bool captured = backend.read(previous);
    if (!backend.owns())
        return Result::ownershipLost;
    // One-shot transmission cannot be safely restored by replaying it.
    if (!captured || previous.image.length != desired.length ||
        (previous.transmit != DipTransmit::disabled &&
         previous.transmit != DipTransmit::bestEffort))
        return Result::rejected;
    if (previous.transmit == DipTransmit::bestEffort &&
        sameDipImage(previous.image, desired))
        return Result::unchanged;

    // Never continue a sequence after ownership is lost, even during rollback.
    auto setTransmit = [&](DipTransmit mode) {
        return backend.owns() && backend.setTransmit(mode) && backend.owns();
    };
    auto write = [&](const DipImage &image) {
        return backend.owns() && backend.write(image) && backend.owns();
    };
    auto verify = [&](const DipImage &image, DipTransmit mode) {
        DipState actual {};
        return backend.owns() && backend.read(actual) && backend.owns() &&
               actual.transmit == mode && sameDipImage(actual.image, image);
    };

    if (setTransmit(DipTransmit::disabled) &&
        write(desired) && verify(desired, DipTransmit::disabled) &&
        setTransmit(DipTransmit::bestEffort) &&
        verify(desired, DipTransmit::bestEffort))
        return Result::applied;

    if (!backend.owns())
        return Result::ownershipLost;
    // A write or even a failed mode change may already have modified state.
    // Restore bytes with transmission disabled, then restore the exact mode.
    if (setTransmit(DipTransmit::disabled) &&
        write(previous.image) && verify(previous.image, DipTransmit::disabled) &&
        setTransmit(previous.transmit) &&
        verify(previous.image, previous.transmit))
        return Result::rolledBack;
    if (!backend.owns())
        return Result::ownershipLost;
    // Best effort only: if rollback failed, try to stop transmission while
    // ownership is still valid. This is NOT a claim of successful restoration.
    (void)setTransmit(DipTransmit::disabled);
    return backend.owns() ? Result::rollbackFailed : Result::ownershipLost;
}
} // namespace HDMIAudioPayload

#endif
