from geometry access markinterval, stickframe;

void mark(path p, frame markframe) {
    draw(p, marker(markinterval(markframe, rotated=true)), p=invisible);
};

void mark(path p, int n=1) {
    mark(p, stickframe(n));
};

