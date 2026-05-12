from collections import deque
class Deque(deque):
    def pop_front(self):
        return self.popleft() if self else None
    
    def push_back(self, item):
        self.append(item)
    
    def is_empty(self):
        return len(self) == 0