(* Like fusion.ml: items of a module without `;;`, then `include` *)
module Kernel = struct

  let kfun x = x

  let kfun2 y =
    let z = y in z

end;;

include Kernel;;
