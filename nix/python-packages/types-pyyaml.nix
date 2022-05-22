{ buildPythonPackage, fetchPypi }:

buildPythonPackage rec {
  pname = "types-PyYAML";
  version = "6.0.5";

  src = fetchPypi {
    inherit pname version;
    sha256 = "Rk4FCRTz0dg6jAOOHPRtpcuWt80C6qCWvKoDZ17dii4=";
  };

  pythonImportsCheck = [ "yaml-stubs" ];
}
