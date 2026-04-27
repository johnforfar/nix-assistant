{
  description = "nix-assistant — rate my Nix config (lint + RAG + local LLM)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  # om CLI overrides nixpkgs with openclaw/nixpkgs (dhcpcd-safe pin).

  outputs = inputs: {
    nixosModules.default =
      { pkgs, lib, ... }:
      let
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          flask
          numpy
        ]);

        # Bundle the assistant Python package into the nix store.
        # PYTHONPATH is set to $out so `import assistant.*` resolves.
        assistantPkg = pkgs.runCommand "nix-assistant-src" {} ''
          mkdir -p $out/assistant
          cp ${./assistant/__init__.py}  $out/assistant/__init__.py
          cp ${./assistant/review.py}    $out/assistant/review.py
          cp ${./assistant/retrieve.py}  $out/assistant/retrieve.py
          cp ${./assistant/lint.py}      $out/assistant/lint.py
        '';

        serverScript = pkgs.writeText "nix-assistant-server.py"
          (builtins.readFile ./assistant/server.py);

        # Downloads embedding index from GitHub Releases on first boot.
        # Runs as ExecStartPre; '-' prefix means failure is non-fatal so
        # the service still starts (lint-only mode) if the download fails.
        fetchScript = pkgs.writeShellScript "nix-assistant-fetch-data" ''
          EMB_DIR=/var/lib/nix-assistant/embeddings
          if [ ! -f "$EMB_DIR/packages.npy" ]; then
            echo "nix-assistant: downloading embedding index from GitHub Releases..."
            mkdir -p "$EMB_DIR"
            BASE=https://github.com/johnforfar/nix-assistant/releases/download/data-v1
            ${pkgs.curl}/bin/curl -fsSL "$BASE/packages.npy"            -o "$EMB_DIR/packages.npy"
            ${pkgs.curl}/bin/curl -fsSL "$BASE/packages_meta.json"      -o "$EMB_DIR/packages_meta.json"
            ${pkgs.curl}/bin/curl -fsSL "$BASE/nixos_options.npy"       -o "$EMB_DIR/nixos_options.npy"
            ${pkgs.curl}/bin/curl -fsSL "$BASE/nixos_options_meta.json" -o "$EMB_DIR/nixos_options_meta.json"
            echo "nix-assistant: embedding index ready."
          fi

          # Ensure the LLM is pulled on the shared hermes-ollama container.
          # /api/pull is idempotent — it's a fast no-op once the blob is present.
          # Required because Ollama 0.20.3 does not lazy-pull on /api/chat.
          MODEL="hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:Q4_K_M"
          OLLAMA_URL="http://hermes-ollama.local:11434"
          echo "nix-assistant: ensuring $MODEL is on $OLLAMA_URL ..."
          ${pkgs.curl}/bin/curl -fsS -X POST "$OLLAMA_URL/api/pull" \
            -H "Content-Type: application/json" \
            --max-time 1200 \
            -d "{\"model\":\"$MODEL\",\"stream\":false}" \
            && echo "nix-assistant: model pull OK" \
            || echo "nix-assistant: model pull failed (server will return 404 until manual pull)"
        '';

        frontendDir = pkgs.runCommand "nix-assistant-frontend" {} ''
          mkdir -p $out
          cp ${./frontend/index.html} $out/index.html
        '';
      in
      {
        config = {
          # ================================================================
          # System user
          # ================================================================
          users.users.nix-assistant = {
            isSystemUser = true;
            group        = "nix-assistant";
          };
          users.groups.nix-assistant = {};

          # ================================================================
          # Flask backend
          # OLLAMA_URL = shared hermes-ollama container (no embedded Ollama).
          # STATIX_BIN / DEADNIX_BIN = full nix store paths (avoid PATH conflict).
          # Embeddings are downloaded from GitHub Releases on first boot via
          # ExecStartPre (fetchScript above).
          # ================================================================
          systemd.services.nix-assistant = {
            description = "nix-assistant — Nix config review (lint + RAG + LLM)";
            after    = [ "network.target" ];
            wantedBy = [ "multi-user.target" ];

            environment = {
              NIX_ASSISTANT_DATA  = "/var/lib/nix-assistant";
              NIX_ASSISTANT_MODEL = "hf.co/OpenxAILabs/nix-reviewer-1.5b-GGUF:Q4_K_M";
              OLLAMA_URL          = "http://hermes-ollama.local:11434";
              PORT                = "5000";
              BIND_HOST           = "127.0.0.1";
              PYTHONPATH          = assistantPkg.outPath;
              STATIX_BIN          = "${pkgs.statix}/bin/statix";
              DEADNIX_BIN         = "${pkgs.deadnix}/bin/deadnix";
            };

            serviceConfig = {
              Type            = "simple";
              ExecStartPre    = "-${fetchScript}";
              ExecStart       = "${pythonEnv}/bin/python ${serverScript}";
              Restart        = "on-failure";
              RestartSec     = "10s";
              User           = "nix-assistant";
              Group          = "nix-assistant";
              StateDirectory = "nix-assistant";
            };
          };

          # ================================================================
          # nginx — port 8080 (host owns 80, Lesson #4)
          # ================================================================
          services.nginx = {
            enable                   = true;
            recommendedGzipSettings  = true;
            recommendedOptimisation  = true;
            recommendedProxySettings = true;

            virtualHosts."default" = {
              default = true;
              listen  = [{ addr = "0.0.0.0"; port = 8080; }];

              locations."/" = {
                root     = frontendDir;
                tryFiles = "$uri /index.html";
              };

              locations."/api/" = {
                proxyPass   = "http://127.0.0.1:5000";
                extraConfig = ''
                  proxy_read_timeout 300s;
                  proxy_send_timeout 300s;
                  proxy_buffering    off;
                '';
              };
            };
          };

          networking.firewall.allowedTCPPorts = [ 8080 ];
        };
      };
  };
}
