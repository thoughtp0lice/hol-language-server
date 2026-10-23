needs "lib/util.ml";;
needs "missing.ml";;

let MY_THM = prove
 (`!n. EVEN n ==> EVEN (n + n)`,
  GEN_TAC THEN
  REWRITE_TAC[EVEN; ADD_SYM_ALT] THEN
  STRIP_TAC THEN ARITH_TAC);;

let x = unknown_function 1;;
