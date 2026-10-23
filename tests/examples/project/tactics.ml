needs "lib/util.ml";;

let th = ADD_SYM_ALT;;

(* A tactic with a parameter named like the global th *)
let HELPER_TAC th =
  REWRITE_TAC[th; ADD_SYM_ALT];;

let MY_TAC =
  let msg = "not \
NOT_A_REFERENCE `ADD_SYM`" in
  fun th -> HELPER_TAC th
let OTHER_TAC = MY_TAC ADD_SYM_ALT;;
