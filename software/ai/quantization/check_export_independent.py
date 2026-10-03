"""Independent check of the EXPORTED files (M3): recompute every golden tile from scratch and compare with the golden hex dumps.

Run from anywhere:  python3 software/ai/quantization/check_export_independent.py     (needs export_rtl.py to have been run)
Reads ONLY hardware/rtl/weights/*.mem, network_params.vh and data/golden/<tile>_{in,L1..L4,out}.hex. Pure Python integers: no numpy,
no torch, no project code, so a bug shared with integer_reference.py or export_rtl.py cannot hide here. It mirrors what the RTL must do
(about 12 s for all tiles). Exits non-zero on the first mismatch.
"""
import glob
import os
import re
import sys
import time

R = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")) + "/"
def mem(path,bits,signed):
    out=[]
    for t in open(path).read().split():
        v=int(t,16)
        if signed and v>=1<<(bits-1): v-=1<<bits
        out.append(v)
    return out
vh=open(R+'hardware/rtl/weights/network_params.vh').read()
P={}
for n in range(1,5):
    g=dict(re.findall(rf'L{n}_(\w+) = (\d+);',vh)); g={k:int(v) for k,v in g.items()}
    g['w']=mem(R+f'hardware/rtl/weights/weights_L{n}.mem',8,True)
    g['b']=mem(R+f'hardware/rtl/weights/bias_L{n}.mem',32,True)
    g['m']=mem(R+f'hardware/rtl/weights/mult_L{n}.mem',16,False)
    P[n]=g
def layer(x,H,W,C,g):                      # x: flat list [y][x][c], valid conv; returns flat [y][x][co], H',W'
    K,CO,CI,dw,sh=g['K'],g['COUT'],g['CIN'],g['DEPTHWISE'],g['SHIFT']; assert C==CI
    oh,ow=H-K+1,W-K+1; out=[0]*(oh*ow*CO); w=g['w']; rnd=1<<(sh-1)
    for y in range(oh):
        for xx in range(ow):
            for co in range(CO):
                acc=g['b'][co]
                if dw:
                    for ky in range(K):
                        for kx in range(K):
                            acc+=x[((y+ky)*W+xx+kx)*C+co]*w[(co*K+ky)*K+kx]
                else:
                    for ci in range(CI):
                        for ky in range(K):
                            base=((y+ky)*W+xx)*C+ci
                            for kx in range(K):
                                acc+=x[base+kx*C]*w[((co*CI+ci)*K+ky)*K+kx]
                v=(acc*g['m'][co]+rnd)>>sh
                out[(y*ow+xx)*CO+co]=0 if v<0 else 255 if v>255 else v
    return out,oh,ow
def run(name,h,wd):
    x=mem(R+f'data/golden/{name}_in.hex',8,False); H,W,C=h+6,wd+6,3; assert len(x)==H*W*3
    for n in range(1,5):
        x,H,W=layer(x,H,W,C,P[n]); C=P[n]['COUT']
        ref=mem(R+f'data/golden/{name}_L{n}.hex',8,False); assert x==ref,(name,'layer',n)
    # pixel shuffle from L4 flat [y][x][12]
    out=[0]*(2*H*2*W*3)
    for y in range(H):
        for xx in range(W):
            for c in range(3):
                for dy in range(2):
                    for dx in range(2):
                        out[((2*y+dy)*(2*W)+2*xx+dx)*3+c]=x[(y*W+xx)*12+4*c+2*dy+dx]
    assert out==mem(R+f'data/golden/{name}_out.hex',8,False),(name,'out')
    print('OK',name,H*2,W*2,flush=True)
t = time.time()
names = sorted(os.path.basename(p)[:-7] for p in glob.glob(R + 'data/golden/*_in.hex'))
if not names:
    sys.exit('no golden tiles: run software/ai/quantization/export_rtl.py first')
for name in names:
    side = round((len(open(R + f'data/golden/{name}_in.hex').read().split()) // 3) ** 0.5)  # (h+6), tiles are square
    run(name, side - 6, side - 6)
print('ALL OK:', len(names), 'tiles, time', round(time.time() - t), 's')
