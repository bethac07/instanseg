FROM mambaorg/micromamba:git-b347535-focal-cuda-12.6.0

USER root

#SETUP
RUN apt-get update && apt-get upgrade -y
RUN apt-get install -y git

USER $MAMBA_USER

#INSTANSEG
RUN git clone https://github.com/instanseg/instanseg.git
WORKDIR instanseg

RUN micromamba create --file env.yml && micromamba clean --all --yes

ENV ENV_NAME=instanseg

#ARG MAMBA_DOCKERFILE_ACTIVATE=1  # (otherwise python will not be found)
#RUN python -c 'import uuid; print(uuid.uuid4())' > /tmp/my_uuid

