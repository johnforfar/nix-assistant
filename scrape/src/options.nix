# Flat attrset keyed by option path, metadata per option.
# Invoked with: nix-instantiate --eval --strict --json -I nixpkgs=<path> src/options.nix
# We walk the options tree manually; avoid nixosOptionsDoc.optionsNix
# because its declaration normalisation triggers store-path lookups.
let
  system = "x86_64-linux";
  pkgs = import <nixpkgs> {
    inherit system;
    config = { allowAliases = false; };
  };
  lib = pkgs.lib;

  eval = import <nixpkgs/nixos/lib/eval-config.nix> {
    inherit system;
    modules = [];
    check = false;
  };

  descriptionText = d:
    if d == null then null
    else if builtins.isAttrs d then (d.text or null)
    else d;

  # Render any value to a string when sane; return null otherwise.
  # Must be total: options.nix is called on every option in the tree,
  # including ones whose example/default is a set/list/function.
  safeRender = v:
    if builtins.isString v then v
    else if builtins.isInt v || builtins.isFloat v then toString v
    else if builtins.isBool v then (if v then "true" else "false")
    else if v == null then null
    else if builtins.isAttrs v || builtins.isList v then
      let r = builtins.tryEval (builtins.toJSON v);
      in if r.success then r.value else null
    else null;

  safeToString = safeRender;

  renderScalar = v:
    if builtins.isString v then v
    else if builtins.isInt v || builtins.isFloat v then toString v
    else if builtins.isBool v then (if v then "true" else "false")
    else null;

  # Every field extraction must be total. NixOS has options whose defaults
  # force the evaluation of sibling options that may be undefined in an
  # empty config. Rather than guard each one, we tryEval every field; on
  # failure the field becomes null and the option is still captured.
  tryFallback = thunk: fallback:
    let r = builtins.tryEval thunk; in
    if r.success then r.value else fallback;

  extractOpt = val: {
    type        = tryFallback (val.type.description or "unspecified") "unspecified";
    description = tryFallback (descriptionText (val.description or null)) null;
    readOnly    = tryFallback (val.readOnly or false) false;
    internal    = tryFallback (val.internal or false) false;
    visible     = tryFallback (if val ? visible then val.visible else true) true;
    loc         = tryFallback (val.loc or []) [];
    hasDefault  = val ? default;
    defaultText = tryFallback
      (if val ? defaultText then
         (let dt = val.defaultText; in
          if builtins.isAttrs dt then (dt.text or null) else renderScalar dt)
       else if val ? default then renderScalar val.default
       else null)
      null;
    hasExample  = val ? example;
    exampleText = tryFallback
      (if val ? example then
         (let e = val.example; in
          if builtins.isAttrs e && e ? text then e.text else renderScalar e)
       else null)
      null;
  };

  collect = path: val:
    if val ? _type && val._type == "option" then
      [{ name = lib.concatStringsSep "." path; value = extractOpt val; }]
    else if lib.isAttrs val && !(val ? _type) then
      lib.concatLists (lib.mapAttrsToList (n: v: collect (path ++ [n]) v) val)
    else [];

in
  builtins.listToAttrs (collect [] eval.options)
