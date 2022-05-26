{ buildPythonPackage
, django_4
, psycopg2
, requests
, sass
}:

buildPythonPackage rec {
  pname = "cookpot";
  version = "0.1.0";

  src = ../..;

  preConfigure = ''
  	${sass}/bin/sass cookpot/static/main.scss:cookpot/static/main.css
  '';

  propagatedBuildInputs = [ django_4 psycopg2 requests ];

  pythonImportsCheck = [ "cookpot" ];
}
