# Test tables for dsp, included by the Makefile: one test-<name> target per entry in FUNCS
# and MODS, driven by the SWEEP_ / NEG_ / XFAIL_ table keyed by that name, all three optional.

MODS  ?= intg iir spec_mux

FUNCS ?= f_abs f_log2 f_logmult f_negate f_qcvt f_round f_s2sm f_sat f_sh f_shleft \
         f_shright f_slogmult f_sm2s f_sx f_sym f_trunc f_umod

# One configuration per word: generation parameters joined by ':', or 'default'.
SWEEP_f_abs      := default IW=2 IW=3 IW=5 IW=16 IW=8:APPROX=1 IW=8:ISYM=1 \
                    IW=8:APPROX=1:ISYM=1 IW=5:APPROX=1:ISYM=1
SWEEP_f_negate   := default IW=2 IW=3 IW=5 IW=16 IW=8:APPROX=1 IW=8:ISYM=1 \
                    IW=8:APPROX=1:ISYM=1 IW=5:APPROX=1:ISYM=1
SWEEP_f_sym      := default IW=2 IW=3 IW=5 IW=16
SWEEP_f_sx       := default IW=12:OW=13 IW=8:OW=9 IW=2:OW=8 IW=5:OW=6 IW=1:OW=2
SWEEP_f_sat      := default IW=8:OW=2 IW=8:OW=3 IW=8:OW=7 IW=5:OW=3 IW=8:OW=6:OSYM=1 \
                    IW=5:OW=3:OSYM=1 IW=16:OW=8 IW=5:OW=8 IW=2:OW=3
SWEEP_f_trunc    := default IW=8:OW=2 IW=8:OW=3 IW=8:OW=6:OSYM=1 IW=5:OW=2 IW=16:OW=8 \
                    IW=4:OW=6 IW=8:OW=8
SWEEP_f_round    := default IW=8:OW=2 IW=8:OW=3 IW=8:OW=6:OSYM=1 IW=5:OW=2 IW=16:OW=8 \
                    IW=8:OW=8 IW=8:OW=9 IW=8:OW=8:OSYM=1
# f_s2sm and f_sm2s give both ports w = min(IW, OW), so a configuration differing only in the
# wider width repeats one already listed. These vary w itself and SM_PLUS.
SWEEP_f_s2sm     := default IW=3:OW=3 IW=16:OW=16 IW=5:OW=5 IW=2:OW=2 IW=8:OW=8:SM_PLUS=0 \
                    IW=8:OW=5:SM_PLUS=0
SWEEP_f_sm2s     := default IW=3:OW=3 IW=16:OW=16 IW=5:OW=5 IW=2:OW=2 IW=8:OW=8:SM_PLUS=0 \
                    IW=8:OW=5:SM_PLUS=0
SWEEP_f_umod     := default IW=2 IW=3 IW=5
SWEEP_f_shleft   := default IW=8:CW=1 IW=8:CW=2 IW=8:CW=4:OSYM=1 IW=5:CW=3 IW=5:CW=3:OSYM=1 \
                    IW=3:CW=2
SWEEP_f_shright  := default IW=8:CW=1 IW=8:CW=2 IW=5:CW=3 IW=3:CW=2 IW=8:CW=4:OSYM=1 \
                    IW=5:CW=3:OSYM=1
SWEEP_f_sh       := default IW=8:CW=1 IW=8:CW=2 IW=8:CW=3 IW=5:CW=3 IW=3:CW=2 IW=16:CW=4
SWEEP_f_log2     := default IW=2 IW=3 IW=5 IW=16 IW=8:ISYM=1 IW=8:APPROX=0 IW=8:LFRAC=1 \
                    IW=8:LFRAC=2 IW=5:LFRAC=2 IW=16:LFRAC=2 IW=8:LFRAC=4
SWEEP_f_slogmult := default AW=5:BW=5 AW=8:BW=4 AW=4:BW=8 AW=3:BW=3 AW=8:BW=8:ISYM=1 \
                    AW=8:BW=8:ZDET=0 AW=8:BW=8:OAPPROX=1 AW=8:BW=8:IAPPROX=0
SWEEP_f_logmult  := default AW=5:BW=5 AW=8:BW=4 AW=8:BW=8:ZDET=1 AW=8:BW=8:ISYM=1 \
                    AW=8:BW=8:OSM=1 AW=8:BW=8:SIGN_ONLY=1 AW=8:BW=8:SIGN_ONLY=1:OSM=1 \
                    AW=8:BW=8:OAPPROX=1 \
                    AW=8:BW=8:IAPPROX=0 AW=8:BW=8:ANTILOG=0 AW=8:BW=8:ANTILOG=0:ZDET=1 \
                    AW=8:BW=8:ANTILOG=0:OSM=1 AW=8:BW=8:ANTILOG=0:ALFRAC=1:BLFRAC=1 \
                    AW=8:BW=8:ANTILOG=1:ALFRAC=1:BLFRAC=1
# The UQ entries widen an unsigned output past the input range, where the largest output
# code needs one bit more than the output width to sit in the signed accumulator.
SWEEP_f_qcvt     := default Q_IN=Q4.12:Q_OUT=Q2.6:ROUND_MODE=half_even \
                    Q_IN=UQ8.8:Q_OUT=UQ4.4:ROUND_MODE=half_up Q_IN=Q3.5:Q_OUT=Q3.9 \
                    Q_IN=Q4.4:Q_OUT=UQ4.4 Q_IN=UQ4.4:Q_OUT=Q4.4 Q_IN=Q4.4:Q_OUT=Q4.4:OSYM=1 \
                    Q_IN=Q4.4:Q_OUT=Q2.2:ROUND_MODE=half_up \
                    Q_IN=Q8.8:Q_OUT=Q1.1:ROUND_MODE=half_even \
                    Q_IN=Q-1.5:Q_OUT=Q0.5 Q_IN=Q1.6:Q_OUT=Q-1.5:ROUND_MODE=half_up \
                    Q_IN=Q-2.6:Q_OUT=Q-1.4:ROUND_MODE=half_even Q_IN=UQ0.4:Q_OUT=UQ-1.3 \
                    Q_IN=Q3.-1:Q_OUT=Q3.0 Q_IN=Q6.-2:Q_OUT=Q4.-2:OSYM=1 Q_IN=Q0.1:Q_OUT=Q0.1 \
                    Q_IN=Q2.5:Q_OUT=Q7.5 Q_IN=UQ4.4:Q_OUT=UQ5.4 Q_IN=UQ4.4:Q_OUT=UQ6.4 \
                    Q_IN=UQ4.4:Q_OUT=UQ12.4 Q_IN=UQ4.4:Q_OUT=UQ12.4:OSYM=1 \
                    Q_IN=UQ4.4:Q_OUT=UQ12.2:ROUND_MODE=half_up \
                    Q_IN=UQ4.4:Q_OUT=UQ12.2:ROUND_MODE=half_even

# intg. EXH_MIN makes the exhaustive sweep's state count a check rather than a number nothing
# reads. The walk reaches every accumulator state only when a legal shift puts a term on its
# lsb: the update's lands at AW-IW-mu, the leak's at AW-LW-lk_mu, and with lk_mu > mu > 0 and
# the default AW=IW+2**MW the update stops at 2, so only the leak reaches zero, and only when
# LW >= IW+1. AW=5 is the sole entry that gets there; the default-AW ones stop at half.
# NEG_APPROX loses three more, an approximate negation never producing the value it folds away.
SWEEP_intg := default OW=4:IW=2:MW=2 OW=8:IW=4:MW=2 OW=12:IW=6:MW=3 OW=16:IW=8:MW=4 \
              OW=8:IW=4:MW=4:AW=12 OW=8:IW=4:MW=4:LW=2 OW=8:IW=4:MW=4:LW=8 \
              NEG_APPROX=1 ISYM=1 OW=6:IW=3:MW=2 NEG_APPROX=1:ISYM=1 \
              OW=4:IW=2:MW=2:EXH=1:EXH_MIN=32 OW=4:IW=2:MW=2:AW=5:EXH=1:EXH_MIN=32 \
              OW=4:IW=2:MW=2:ISYM=1:EXH=1:EXH_MIN=32 \
              OW=4:IW=2:MW=2:NEG_APPROX=1:EXH=1:EXH_MIN=29

# One entry per rejecting check, in table order. MW >= 2 because lk_mu > mu > 0 needs two
# values above zero. LW defaults to OW>>1, so OW=3 and OW=2 both leave a one-bit leak word
# whose signed negation is zero either way. The EXH pair is ordered: the default is small
# enough for AW but far too large for the vector count, and the AW entry keeps the vector
# count small so the AW guard is the one that fires.
NEG_intg := OW=8:IW=4:MW=1 OW=1 OW=2:IW=8:AW=4 OW=4:IW=2:MW=2:AW=6:LW=8 OW=3 OW=2 \
            OW=4:IW=2:MW=1 OW=4:IW=2:MW=6:AW=20 OW=4:IW=2:MW=2:AW=64 EXH=1 \
            OW=4:IW=2:MW=2:AW=23:EXH=1

# iir. mu=0 is never driven: above a filter factor of one the accumulator provably overflows,
# so the module constrains mu > 0. The filter converges toward its input, so the states at both
# ends of the range are reached only by the transient one vector stands for and the walk
# settles into the middle -- 242 of 256 at IW=4, the same shortfall of 14 at every width below.
SWEEP_iir := default ARST=0 IW=4:OW=4:MW=2 IW=4:OW=6:MW=2 IW=8:OW=4:MW=4 \
             IW=8:OW=24:MW=4 IW=2:OW=2:MW=1 IW=12:OW=12:MW=3 IW=16:OW=8:MW=5 \
             IW=4:OW=4:MW=2:EXH=1:EXH_MIN=242 IW=3:OW=3:MW=2:EXH=1:EXH_MIN=114 \
             IW=2:OW=2:MW=2:EXH=1:EXH_MIN=50 \
             IW=4:OW=4:MW=2:ARST=0:EXH=1:EXH_MIN=242 IW=4:OW=6:MW=2:EXH=1:EXH_MIN=242

# spec_mux. LOOKAHEAD is bounded by N_SYM-1: 0, 1 and 31 take the plain chain, one level of
# composition, and the bound itself. PAM_N=3 clog2s to the default SYM_W without using its top
# code; PAM_N=16 is the accepted edge of the bound whose rejection at 17 heads NEG_spec_mux.
# PAM_N=2:N_HIST=6 is Parhi's six-tap DFE, a 64-to-1 loop. N_SYM=5:LOOKAHEAD=2 leaves the last
# group of symbols short of the look-ahead stride. N_SYM=256:PAM_N=6 is the widest block swept,
# 768 bits of res, compared in 13 chunks.
SWEEP_spec_mux := default LOOKAHEAD=0 LOOKAHEAD=1 LOOKAHEAD=31 N_SYM=1:LOOKAHEAD=0 \
                  N_SYM=2:LOOKAHEAD=1 N_SYM=5:LOOKAHEAD=2 PAM_N=2 PAM_N=3 PAM_N=8 \
                  PAM_N=16 N_HIST=2 PAM_N=2:N_HIST=6 PAM_N=2:N_HIST=6:LOOKAHEAD=3 \
                  PIPE_LA=1 PIPE_LA=1:LOOKAHEAD=0 RST_STATE=3 RST_STATE=2:PIPE_LA=1 \
                  PAM_N=3:N_HIST=2:PIPE_LA=1 PAM_N=16:N_HIST=2:N_SYM=4:LOOKAHEAD=1 \
                  PAM_N=2:N_SYM=4:LOOKAHEAD=1:EXH=1 PAM_N=2:N_SYM=8:LOOKAHEAD=2:EXH=1 \
                  UNROLL=0 UNROLL=0:LOOKAHEAD=0 UNROLL=0:PIPE_LA=1 \
                  UNROLL=0:N_SYM=5:LOOKAHEAD=2 UNROLL=0:PAM_N=2:N_HIST=6 \
                  N_SYM=256:PAM_N=6

# One entry per rejecting check, in table order. The N_ENTRIES > MAX_NETS guard is checked
# three ways: an explicit small cap, the same cap under UNROLL=0 to show it holds independent
# of the emitted RTL shape, and PAM_N=16:N_HIST=4 blowing the default budget (3997696 entries)
# without touching MAX_NETS at all.
NEG_spec_mux := PAM_N=1 PAM_N=17 N_HIST=0 N_SYM=0 LOOKAHEAD=-1 LOOKAHEAD=32 RST_STATE=4 \
                MAX_NETS=10 UNROLL=0:MAX_NETS=10 PAM_N=16:N_HIST=4 EXH=1

# One per width check the module makes, then the testbench's own. A one-bit signed input has
# no magnitude bit under its sign; MW=0 leaves the mu port no bits; OW above IW+2**MW would
# slice below the accumulator's lsb. The EXH pair is ordered: the default is small enough for W
# but needs far too many clocks, and the W entry pins EXH_HOLD so the W guard is the one that
# fires.
NEG_iir := IW=1 MW=0 OW=0 IW=4:OW=9:MW=2 IW=2:OW=2:MW=6 IW=32:OW=8:MW=5 EXH=1 \
           IW=7:OW=7:MW=4:EXH=1:EXH_HOLD=1

# f_sat has nothing to saturate at equal widths and f_sx nothing to extend when the output is
# no wider; both error rather than emit an empty slice. f_sat and f_round derive the output
# width as iwidth-1 when the requested one is no narrower, so IW=1 leaves them nothing.
NEG_f_sat   := IW=8:OW=8 IW=1:OW=2
NEG_f_sx    := IW=8:OW=8 IW=8:OW=4
NEG_f_round := IW=1:OW=2

# A zero-width output has no sign bit to hold the truncated value. The testbench rejects
# it first: it derives the reference output range from OW before it includes f_trunc.
NEG_f_trunc := OW=0

# Sign magnitude needs a sign bit and at least one magnitude bit, so the width the two
# conversions share -- the narrower of IW and OW -- must be at least 2.
NEG_f_s2sm := IW=8:OW=1
NEG_f_sm2s := IW=8:OW=1

# A zero-width shift control has no bits to shift by: all three would part-select sh[-1:0],
# and f_sh would size its accumulator from 2**(cwidth-1), not an integer at cwidth=0.
NEG_f_sh      := CW=0
NEG_f_shleft  := CW=0
NEG_f_shright := CW=0

# f_log2 needs a sign bit and one magnitude bit, and its reference caps lfrac where generation
# cost stops being worth it. Both multipliers log an input, so each logged width has the same
# lower bound. A signed format with no integer bit (Q0.1, Q-1.5) is accepted, the sign living
# in the width rather than in m.
NEG_f_log2     := IW=1 LFRAC=13
NEG_f_logmult  := AW=1 BW=1
NEG_f_slogmult := BW=1
NEG_f_qcvt     := Q_IN=X4.4 ROUND_MODE=nearest Q_OUT=Q0.0 Q_IN=Q2.-2

# Configurations known to mismatch. A listed one that MISMATCHES reports XFAIL and does not
# turn make test red; one that PASSES reports XPASS and does, so settling a finding forces this
# table to be updated. One that fails to generate, build or run reports ERROR and still turns
# make test red -- XFAIL excuses a wrong answer, never a missing one.
