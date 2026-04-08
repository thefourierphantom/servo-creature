
def clamp(value, low, high):
    return max(low, min(high, value))

def slew_limit(current, target, max_step):
    if target > current + max_step:
        return current + max_step
    if target < current - max_step:
        return current - max_step
    return target
