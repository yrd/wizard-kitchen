{
	description = "Automatic literature surveying";

	inputs.nixpkgs.url = "nixpkgs/nixpkgs-unstable";
	inputs.flake-utils.url = "github:numtide/flake-utils";

	outputs = { self, nixpkgs, flake-utils }: (flake-utils.lib.eachDefaultSystem (system:
	  let
      pkgs = import nixpkgs { inherit system; };

      pythonDependencies = (pythonPackages: with pythonPackages; [
      	# Runtime
        django_4
        psycopg2
        requests
        # Tests
        hypothesis
        pytest
        # Type checking, linting and formatting
				django-stubs
				mypy
        black
        isort
        types-requests
        # Documentation
        sphinx
        sphinx_rtd_theme
      ]);

      python = (pkgs.python310.override {
      	packageOverrides = self: super: {
					django-stubs = self.callPackage ./nix/python-packages/django-stubs.nix {};
					django-stubs-ext = self.callPackage ./nix/python-packages/django-stubs-ext.nix {};
					types-PyYAML = self.callPackage ./nix/python-packages/types-pyyaml.nix {};
      	};
      }).withPackages pythonDependencies;
    in rec {
      packages = {
        devEnv = pkgs.symlinkJoin {
        	name = "cookpot-env";
        	paths = [ python pkgs.nodePackages.sass pkgs.nodePackages.prettier ];
        };

        requirementsFile = let
          pythonWithPip = python.withPackages (pythonPackages:
            [ pythonPackages.pip ]
            ++ (pythonDependencies pythonPackages));
        in pkgs.runCommand "requirements.txt" {} ''
          ${pythonWithPip}/bin/python -m pip freeze
          ${pythonWithPip}/bin/python -m pip freeze \
            | ${pkgs.perl}/bin/perl -pe 's, @ file:///build/.*?-((\d+\.)*\d+)/.*$,==\1,g' \
            | ${pkgs.perl}/bin/perl -pe 's, @ file:///build/source.*?/dist/.*?-((\d+\.)*\d+).*\.whl$,==\1,g' \
            > $out
        '';

        release = (pkgs.python310.override {
					packageOverrides = self: super: {
						cookpot = self.callPackage ./nix/python-packages/cookpot.nix {
							sass = pkgs.nodePackages.sass;
						};
					};
				}).withPackages (pythonPackages: [ pythonPackages.cookpot ]);
      };

      devShell = python.env;
		}));
}
