{
  description = "nix-assistant — rate my Nix config (lint + RAG + local LLM)";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  # om CLI overrides nixpkgs with openclaw/nixpkgs (dhcpcd-safe pin).
  # No other inputs needed — dhcpcd/container plumbing is in the om wrapper.

  outputs = inputs: {
    nixosModules.default =
      { pkgs, lib, ... }:
      let
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          flask
          numpy
        ]);

        # Bundle the assistant package into the nix store so server.py
        # can import it via PYTHONPATH.
        assistantPkg = pkgs.runCommand "nix-assistant-src" {} ''
          mkdir -p $out/assistant
          cp ${./assistant/__init__.py}  $out/assistant/__init__.py
          cp ${./assistant/review.py}    $out/assistant/review.py
          cp ${./assistant/retrieve.py}  $out/assistant/retrieve.py
          cp ${./assistant/lint.py}      $out/assistant/lint.py
        '';

        serverScript = pkgs.writeText "nix-assistant-server.py"
          (builtins.readFile ./assistant/server.py);

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
            group = "nix-assistant";
          };
          users.groups.nix-assistant = {};

          # ================================================================
          # Flask backend
          #
          # Data lives in StateDirectory (/var/lib/nix-assistant/).
          # Push once after deploy:
          #   scp scrape/data/corpus.db <xnode>:/var/lib/nix-assistant/
          #   scp -r assistant/data/embeddings/ <xnode>:/var/lib/nix-assistant/
          #
          # OLLAMA_URL points to the shared hermes-ollama container.
          # No embedded Ollama — one Ollama per Xnode.
          # ================================================================
          systemd.services.nix-assistant = {
            description = "nix-assistant — Nix config review (lint + RAG + LLM)";
            after    = [ "network.target" ];
            wantedBy = [ "multi-user.target" ];

            environment = {
              NIX_ASSISTANT_DATA  = "/var/lib/nix-assistant";
              NIX_ASSISTANT_MODEL = "llama3.2:1b";
              OLLAMA_URL          = "http://hermes-ollama.local:11434";
              PORT                = "5000";
              BIND_HOST           = "127.0.0.1";
              PYTHONPATH          = assistantPkg.outPath;
              # statix + deadnix on PATH for lint.py
              PATH = lib.makeBinPath [
                pkgs.statix
                pkgs.deadnix
                pkgs.coreutils
              ];
            };

            serviceConfig = {
              Type           = "simple";
              ExecStart      = "${pythonEnv}/bin/python ${serverScript}";
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
            enable = true;
            recommendedGzipSettings    = true;
            recommendedOptimisation    = true;
            recommendedProxySettings   = true;

            virtualHosts."_" = {
              default = true;
              listen = [{ addr = "0.0.0.0"; port = 8080; }];

              locations."/" = {
                root    = frontendDir;
                tryFiles = "$uri /index.html";
              };

              locations."/api/" = {
                proxyPass  = "http://127.0.0.1:5000";
                extraConfig = ''
                  proxy_read_timeout 300s;
                  proxy_send_timeout 300s;
                  proxy_buffering off;
                '';
              };
            };
          };

          networking.firewall.allowedTCPPorts = [ 8080 ];
        };
      };
  };
}
