{ buildPythonPackage
, fetchPypi
, django_4
, mypy
, toml
, typing-extensions
}:

buildPythonPackage rec {
  pname = "django-stubs-ext";
  version = "0.4.0";

  src = fetchPypi {
    inherit pname version;
    sha256 = "MQTEdIw0vXQcMQo+avkN/7pG5BvMviQ4luOKcIJih2s=";
  };

  preBuild = ''
    sed -ie 's~license_file = ../LICENSE.txt~~g' setup.cfg
  '';

  propagatedBuildInputs = [ django_4 toml typing-extensions ];

  pythonImportsCheck = [ "django_stubs_ext" ];
}
