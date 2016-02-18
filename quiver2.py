import numpy as np

# TODO: cache BandedMatrix calls
# TODO: test BandedMatrix
# TODO: improve slicing and arithmetic operations of BandedMatrix
# TODO: port to Julia and compare speed

# TODO: use faster version of partial order aligner
# TODO: benchmark against actual quiver implementation


class BandedMatrix:
    """A sparse banded matrix.

    Band is always wide enough to include [0, 0] and [-1, -1].

    Currently only supports limited slicing and no arithmetic
    operations.

    Warning: does not do bounds checks.

    """

    def __init__(self, shape, bandwidth=0):
        nrows, ncols = shape
        if not nrows > 0 and ncols > 0:
            raise Exception('shape is not positive: {}'.format(shape))
        self.shape = shape
        self.bandwidth = bandwidth
        self.diff = np.abs(nrows - ncols)
        data_nrows = 2 * bandwidth + self.diff + 1
        self.data = np.zeros((data_nrows, ncols))
        self.h_offset = max(ncols - nrows, 0)
        self.v_offset = max(nrows - ncols, 0)

    @property
    def nrows(self):
        return self.shape[0]

    @property
    def ncols(self):
        return self.shape[1]

    def data_row(self, i, j):
        return (i - j) + self.h_offset + self.bandwidth

    def get_elt(self, i, j):
        row = self.data_row(i, j)
        return self.data[row, j]

    def row_range(self, j):
        start = max(0, j - self.h_offset - self.bandwidth)
        stop = min(j + self.v_offset + self.bandwidth + 1, self.nrows)
        return start, stop

    def data_row_range(self, j):
        start = max(0, self.h_offset + self.bandwidth - j)
        a, b = self.row_range(j)
        stop = start + (b - a)
        return start, stop

    def get_col(self, j):
        result = np.zeros(self.nrows)
        start, stop = self.row_range(j)
        dstart, dstop = self.data_row_range(j)
        result[start:stop] = self.data[dstart:dstop, j]
        return result

    def __setitem__(self, key, val):
        # TODO: implement multidim slicing and negative indices
        i, j = key
        row = self.data_row(i, j)
        self.data[row, j] = val

    def inband(self, i, j):
        row = self.data_row(i, j)
        return 0 <= row < self.data.shape[0]

    def full(self):
        # this is slow, but just for testing purposes
        result = np.zeros((self.nrows, self.ncols))
        for i in range(self.nrows):
            for j in range(self.ncols):
                if not self.inband(i, j):
                    continue
                row = self.data_row(i, j)
                result[i, j] = self.data[row, j]
        return result

    def flip(self):
        self.data = np.flipud(np.fliplr(self.data))


def update(arr, i, j, s_base, t_base, log_p, log_ins, log_del):
    # TODO: log(1-p) may not be negligible
    sub = (0 if s_base == t_base else log_p)
    scores = []
    if arr.inband(i - 1, j):
        # insertion
        scores.append(arr.get_elt(i - 1, j) + log_ins)
    if arr.inband(i, j - 1):
        # deletion
        scores.append(arr.get_elt(i, j - 1) + log_del)
    if arr.inband(i - 1, j - 1):
        scores.append(arr.get_elt(i - 1, j - 1) + sub)
    return max(scores)


def forward(s, log_p, t, log_ins, log_del, bandwidth):
    result = BandedMatrix((len(s) + 1, len(t) + 1), bandwidth)
    for i in range(min(result.shape[0], result.v_offset + bandwidth + 1)):
        result[i, 0] = log_ins * i
    for j in range(min(result.shape[1], result.h_offset + bandwidth + 1)):
        result[0, j] = log_del * j
    # TODO: reverse order of iteration?
    for j in range(1, result.ncols):
        start, stop = result.row_range(j)
        start = max(start, 1)
        for i in range(start, stop):
            result[i, j] = update(result, i, j, s[i-1], t[j-1], log_p[i-1], log_ins, log_del)
    return result


def backward(s, log_p, t, log_ins, log_del, bandwidth):
    s = ''.join(reversed(s))
    log_p = np.array(list(reversed(log_p)))
    t = ''.join(reversed(t))
    result = forward(s, log_p, t, log_ins, log_del, bandwidth)
    result.flip()
    return result


def updated_col(pos, base, template, seq, log_p, A, log_ins, log_del):
    j = pos + 1
    result = np.zeros(A.nrows)
    if j < A.h_offset + A.bandwidth:
        result[0] = log_del * j
    start, stop = A.row_range(j)
    # TODO: code duplication with `update()`
    for i in range(start, stop):
        sub = (0 if base == seq[i-1] else log_p[i-1])
        scores = []
        if A.inband(i - 1, j):
            # insertion
            scores.append(result[i - 1] + log_ins)
        if A.inband(i, j - 1):
            # deletion
            scores.append(A.get_elt(i, j - 1) + log_del)
        if A.inband(i - 1, j - 1):
            scores.append(A.get_elt(i - 1, j - 1) + sub)
        result[i] = max(scores)
    return result


def score_mutation(mutation, template, seq, log_p, A, B, log_ins, log_del, bandwidth):
    """Score a mutation using the forward-backward trick."""
    # FIXME: account for different size of array for an insertion or deletion
    mtype, pos, base = mutation
    if mtype == 'deletion':
        aj = pos
        Acol = A.get_col(aj)
    else:
        aj = pos + 1
        Acol = updated_col(pos, base, template, seq, log_p, A, log_ins, log_del)
    bj = pos + (0 if mtype == 'insertion' else 1)
    Bcol = B.get_col(bj)

    # need to chop off beginning of Acol and end of Bcol and align
    a_start, a_stop = A.row_range(aj)
    b_start, b_stop = B.row_range(bj)

    start = max(a_start, b_start)
    stop = min(a_stop, b_stop)
    return (Acol[start:stop] + Bcol[start:stop]).max()


def mutations(template):
    """Returns (name, position, base)"""
    for j in range(len(template)):
        for base in 'ACGT':
            if template[j] == base:
                continue
            yield ['substitution', j, base]
        yield ['deletion', j, None]
        for base in 'ACGT':
            yield ['insertion', j, base]
    # insertion after last
    for base in 'ACGT':
        yield ['insertion', len(template), base]


def update_template(template, mutation):
    mtype, pos, base = mutation
    if mtype == 'substitution':
        return ''.join([template[:pos], base, template[pos + 1:]])
    elif mtype == 'insertion':
        return ''.join([template[:pos], base, template[pos:]])
    elif mtype == 'deletion':
        return ''.join([template[:pos], template[pos + 1:]])
    else:
        raise Exception('unknown mutation: {}'.format(mtype))


def apply_mutations(template, mutations):
    for i in range(len(mutations)):
        score, mutation = mutations[i]
        template = update_template(template, mutation)
        mtype, pos, _ = mutation
        if mtype == 'insertion':
            for ii in range(i + 1, len(mutations)):
                if mutations[ii][1][1] > pos:
                    mutations[ii][1][1] += 1
        elif mtype == 'deletion':
            for ii in range(i + 1, len(mutations)):
                if mutations[ii][1][1] > pos:
                    mutations[ii][1][1] -= 1
    return template


def choose_candidates(candidates, min_dist):
    final_cands = []
    posns = set()
    for c in reversed(sorted(candidates, key=lambda c: c[0])):
        _, (_, posn, _) = c
        if any(abs(posn - p) < min_dist for p in posns):
            continue
        posns.add(posn)
        final_cands.append(c)
    return final_cands


def quiver2(template, sequences, phreds, log_ins, log_del, bandwidth=10,
            min_dist=9, max_iters=100, verbose=False):
    """Generate an alignment-free consensus.

    sequences: list of dna sequences

    phreds: list of arrays of phred scores

    """
    log_ps = list((-phred / 10) for phred in phreds)

    if bandwidth < 0:
        raise Exception('bandwidth cannot be negative: {} '.format(bandwidth))

    if verbose:
        print("computing initial alignments")
    As = list(forward(s, p, template, log_ins, log_del, bandwidth) for s, p in zip(sequences, log_ps))
    Bs = list(backward(s, p, template, log_ins, log_del, bandwidth) for s, p in zip(sequences, log_ps))
    best_score = sum(A[-1, -1] for A in As)
    for i in range(max_iters):
        old_score = best_score
        if verbose:
            print("iteration {}".format(i))
        candidates = []
        for mutation in mutations(template):
            score = sum(score_mutation(mutation, template, seq, log_p, A, B, log_ins, log_del, bandwidth)
                        for seq, log_p, A, B in zip(sequences, log_ps, As, Bs))
            if score > best_score:
                candidates.append([score, mutation])
        if not candidates:
            break
        if verbose:
            print("  found {} candidate mutations".format(len(candidates)))
        chosen_cands = choose_candidates(candidates, min_dist)
        template = apply_mutations(template, chosen_cands)
        As = list(forward(s, p, template, log_ins, log_del, bandwidth) for s, p in zip(sequences, log_ps))
        Bs = list(backward(s, p, template, log_ins, log_del, bandwidth) for s, p in zip(sequences, log_ps))
        best_score = sum(A[-1, -1] for A in As)

        # detect if a single mutation is better
        # FIXME: code duplication
        if best_score < chosen_cands[0][0]:
            if verbose:
                print('  rejecting multiple candidates in favor of best')
            chosen_cands = [chosen_cands[0]]
            template = apply_mutations(template, chosen_cands)
            As = list(forward(s, p, template, log_ins, log_del, bandwidth) for s, p in zip(sequences, log_ps))
            Bs = list(backward(s, p, template, log_ins, log_del, bandwidth) for s, p in zip(sequences, log_ps))
            best_score = sum(A[-1, -1] for A in As)
            assert best_score == chosen_cands[0][0]
        if verbose:
            print('  kept {} mutations'.format(len(chosen_cands)))
            print('  score: {:.4f}'.format(best_score))
        assert best_score > old_score
    return template
