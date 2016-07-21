module Util

export p_to_phred, phred_to_log_p, phred_to_p

function p_to_phred(p::Float64)
    return Int8(min(round(-10.0 * log10(p)), typemax(Int8)))
end

function p_to_phred(x::Vector{Float64})
    return Int8[p_to_phred(p) for p in x]
end

@generated function phred_to_log_p(x)
    return quote
        return x / (-10.0)
    end
end

function phred_to_p(q::Float64)
    return exp10(phred_to_log_p(q))
end

function phred_to_p(x::Vector{Float64})
    return exp10(phred_to_log_p(x))
end

end
