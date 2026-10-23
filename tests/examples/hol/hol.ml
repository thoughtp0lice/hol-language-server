(* A minimal stand-in for the HOL Light directory *)
let ADD_SYM = prove
 (`!m n. m + n = n + m`,
  ARITH_TAC);;

let EVEN = new_definition `EVEN n <=> ?m. n = 2 * m`;;
