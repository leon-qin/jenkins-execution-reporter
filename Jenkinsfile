pipeline {
    agent none
    stages {
        stage('Hello') {
            agent {
                label "testlabel"
            }
            steps {
                echo 'Hello World'
            }
        }
        stage('Hello2') {
                parallel {
                        stage("p1") {
                            agent any
                            steps {
                                echo "P1"
                            }
                        }
                        stage("p2")  {
                            agent any
                            steps {
                                echo "P2"
                            }
                        }
                        stage("p3") {
                            agent any
                            steps {
                                echo "P3"
                            }
                        }
                    
    
            }
        }
        stage('Hello3') {
            agent {
                label "testlabel"
            }
            steps {
                error 'This is an error'
            }
        }
    }
}
