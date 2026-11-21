//; a = generate('cl', 'u_a')
//; b = clone(a, 'u_b')
//; c = clone(a, 'u_c')
module `mname` ();
    `a.instantiate()`
    `b.instantiate()`
    `c.instantiate()`
endmodule
