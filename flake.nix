{
  description = "nix-assistant — rate my Nix config (lint + RAG + local LLM)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = inputs: {
    nixosModules.default =
      { pkgs, lib, ... }:
      let
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          flask
          numpy
        ]);

        backendApp = pkgs.writeText "nix-assistant-app.py" (
          builtins.readFile ./assistant/server.py
        );

        # Bundle the assistant package files into the nix store so the
        # server.py can import them at runtime.
        assistantPkg = pkgs.runCommand "nix-assistant-pkg" {} ''
          mkdir -p $out/assistant
          cp ${./assistant/__init__.py}  $out/assistant/__init__.py
          cp ${./assistant/review.py}    $out/assistant/review.py
          cp ${./assistant/retrieve.py}  $out/assistant/retrieve.py
          cp ${./assistant/lint.py}      $out/assistant/lint.py
        '';
      in
      {
        config = {
          # ================================================================
          # Ollama — reuses the existing instance if already enabled.
          # Support-agent already pulls llama3.2:1b + nomic-embed-text.
          # We only ensure those models are listed; NixOS deduplicates.
          # ================================================================
          services.ollama = {
            enable = true;
            loadModels = [
              "llama3.2:1b"
              "nomic-embed-text"
            ];
          };

          # ================================================================
          # System user
          # ================================================================
          users.users.nix-assistant = {
            isSystemUser = true;
            group = "nix-assistant";
          };
          users.groups.nix-assistant = {};

          # ================================================================
          # nix-assistant backend
          # Data (corpus.db + embeddings/) lives in the StateDirectory.
          # Push it once after deploy:
          #   rsync -r scrape/data/corpus.db assistant/data/embeddings/ \
          #     root@<xnode>:/var/lib/nix-assistant/
          # ================================================================
          systemd.services.nix-assistant = {
            description = "nix-assistant — Nix config review (lint + RAG + LLM)";
            after = [ "ollama.service" "network.target" ];
            wants = [ "ollama.service" ];
            wantedBy = [ "multi-user.target" ];

            environment = {
              NIX_ASSISTANT_DATA  = "/var/lib/nix-assistant";
              NIX_ASSISTANT_MODEL = "llama3.2:1b";
              OLLAMA_URL          = "http://127.0.0.1:11434";
              PORT                = "5001";
              BIND_HOST           = "127.0.0.1";
              # statix + deadnix must be on PATH for lint.py
              PATH = lib.makeBinPath [
                pkgs.statix
                pkgs.deadnix
                pkgs.coreutils
              ];
              PYTHONPATH = assistantPkg.outPath;
            };

            serviceConfig = {
              Type             = "simple";
              ExecStart        = "${pythonEnv}/bin/python ${backendApp}";
              Restart          = "on-failure";
              RestartSec       = "10s";
              User             = "nix-assistant";
              Group            = "nix-assistant";
              StateDirectory   = "nix-assistant";
              WorkingDirectory = "/var/lib/nix-assistant";
            };
          };

          # ================================================================
          # nginx — add location block alongside support-agent
          # ================================================================
          services.nginx.virtualHosts."default".locations."/nix/" = {
            root = "${./frontend}";
            tryFiles = "$uri /index.html";
          };

          services.nginx.virtualHosts."default".locations."/api/review" = {
            proxyPass = "http://127.0.0.1:5001";
            extraConfig = ''
              proxy_read_timeout 300s;
              proxy_send_timeout 300s;
              proxy_buffering off;
            '';
          };
        };
      };
  };
}
