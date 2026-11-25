// Wait adapter for thread contexts that may sleep. Never use in IRQ context.
#ifndef KERN_SLEEPABLE_DELAY_HPP
#define KERN_SLEEPABLE_DELAY_HPP
namespace XELP {
template<class SleepMs, class BusyUs>
inline void sleepableDelayUs(unsigned us, SleepMs sleepMs, BusyUs busyUs) {
    const unsigned milliseconds = us / 1000;
    const unsigned remainder = us % 1000;
    if (milliseconds) sleepMs(milliseconds);
    if (remainder) busyUs(remainder);
}
}
#endif
