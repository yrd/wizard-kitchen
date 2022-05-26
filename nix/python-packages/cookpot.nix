{ buildPythonPackage
, django_4
, psycopg2
, requests
}:

buildPythonPackage rec {
  pname = "cookpot";
  version = "0.1.0";

  src = ../..;

  propagatedBuildInputs = [ django_4 psycopg2 requests ];

  pythonImportsCheck = [ "cookpot" ];
}
