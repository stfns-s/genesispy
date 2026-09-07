# line 1 "INPUT"
x = f(1,
# line 2 "INPUT"
        2)
# line 3 "INPUT"
self.emit("wire w;")
# line 4 "INPUT"
for i in (1,
# line 5 "INPUT"
        2):
# line 6 "INPUT"
    self.emit(f"assign a_{ i } = { i };")
# line 7 "INPUT"
# endfor
