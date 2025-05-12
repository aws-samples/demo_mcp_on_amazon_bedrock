import * as cdk from 'aws-cdk-lib';
import * as ec2 from 'aws-cdk-lib/aws-ec2';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as elbv2 from 'aws-cdk-lib/aws-elasticloadbalancingv2';
import * as autoscaling from 'aws-cdk-lib/aws-autoscaling';
import { Construct } from 'constructs';

export interface BedrockMcpStackProps extends cdk.StackProps {
  namePrefix?: string;
}

export class BedrockMcpStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: BedrockMcpStackProps) {
    super(scope, id, props);

    const prefix = props?.namePrefix || 'MCP';

    // Create VPC
    const vpc = new ec2.Vpc(this, `${prefix}-VPC`, {
      maxAzs: 2,
      natGateways: 1,
      subnetConfiguration: [
        {
          name: 'Public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'Private',
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
          cidrMask: 24,
        }
      ]
    });

    // Create Security Group
    const sg = new ec2.SecurityGroup(this, `${prefix}-SG`, {
      vpc,
      allowAllOutbound: true,
      description: 'Security group for MCP services'
    });

    sg.addIngressRule(
      ec2.Peer.anyIpv4(),
      ec2.Port.tcp(8502),
      'Streamlit UI'
    );

    // Create IAM Role
    const role = new iam.Role(this, 'EC2-Role', {
      assumedBy: new iam.ServicePrincipal('ec2.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonSSMManagedInstanceCore')
      ]
    });

    role.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel*',
        'bedrock:ListFoundationModels'
      ],
      resources: ['*']
    }));

    // Create Application Load Balancer
    const alb = new elbv2.ApplicationLoadBalancer(this, `${prefix}-ALB`, {
      vpc,
      internetFacing: true
    });

    // Create ALB Listeners
    const streamlitListener = alb.addListener('Streamlit', { 
      port: 8502,
      protocol: elbv2.ApplicationProtocol.HTTP
    });

    // Create IAM User for API Access with dynamic name
    const apiUser = new iam.User(this, 'BedrockApiUser', {
      userName: `bedrock-mcp-api-user-${cdk.Stack.of(this).stackName}`
    });

    apiUser.addToPolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: [
        'bedrock:InvokeModel*',
        'bedrock:ListFoundationModels'
      ],
      resources: ['*']
    }));

    // Create access key for the user
    const accessKey = new iam.CfnAccessKey(this, 'BedrockApiAccessKey', {
      userName: apiUser.userName
    });

    // Create User Data with improved initialization
    const userData = ec2.UserData.forLinux();
    userData.addCommands(
      '#!/bin/bash',
      
      // Set HOME and PATH environment variables first
      'export HOME=/root',
      'export PATH="/usr/local/bin:$PATH"',
      
      // Update and install dependencies
      'apt-get update',
      'apt-get install -y software-properties-common',
      'add-apt-repository -y ppa:deadsnakes/ppa',
      'apt-get update',
      'apt-get install -y python3.12 python3.12-venv git',
      
      
      // Install Node.js
      'curl -fsSL https://deb.nodesource.com/setup_22.x | bash -',
      'apt-get install -y nodejs',
      
      // Install UV for ubuntu user
      'su - ubuntu -c "curl -LsSf https://astral.sh/uv/install.sh | sh"',
      'echo \'export PATH="/home/ubuntu/.local/bin:$PATH"\' >> /home/ubuntu/.bashrc',
      
      // Create and set up project directory with proper ownership
      'mkdir -p /home/ubuntu/demo_mcp_on_amazon_bedrock',
      'chown ubuntu:ubuntu /home/ubuntu/demo_mcp_on_amazon_bedrock',
      'cd /home/ubuntu/demo_mcp_on_amazon_bedrock',
      
      // Clone project with HTTPS and retry logic
      'MAX_RETRIES=3',
      'RETRY_COUNT=0',
      'while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do',
      '    git clone https://github.com/aws-samples/demo_mcp_on_amazon_bedrock.git . && break',
      '    RETRY_COUNT=$((RETRY_COUNT+1))',
      '    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then',
      '        echo "Git clone attempt $RETRY_COUNT failed, retrying in 5 seconds..."',
      '        sleep 5',
      '    fi',
      'done',
      
      // Exit if git clone ultimately failed
      '[ -z "$(ls -A /home/ubuntu/demo_mcp_on_amazon_bedrock)" ] && echo "Failed to clone repository" && exit 1',
      
      // Create necessary directories with proper ownership
      'mkdir -p logs tmp',
      'chown -R ubuntu:ubuntu /home/ubuntu/demo_mcp_on_amazon_bedrock',
      'chmod 755 /home/ubuntu/demo_mcp_on_amazon_bedrock',
      'chmod 755 logs tmp',

      // Setup Python environment as ubuntu user
      'su - ubuntu -c "cd /home/ubuntu/demo_mcp_on_amazon_bedrock && \
        python3.12 -m venv .venv && \
        source .venv/bin/activate && \
        source /home/ubuntu/.bashrc && \
        uv pip install ."',

      // Configure environment with proper ownership
      'cat > .env << EOL',
      `AWS_ACCESS_KEY_ID=${accessKey.ref}`,
      `AWS_SECRET_ACCESS_KEY=${accessKey.attrSecretAccessKey}`,
      'AWS_REGION=' + cdk.Stack.of(this).region,
      'LOG_DIR=./logs',
      'CHATBOT_SERVICE_PORT=8502',
      'MCP_SERVICE_HOST=127.0.0.1',
      'MCP_SERVICE_PORT=7002',
      `API_KEY=${cdk.Names.uniqueId(this)}`,
      'EOL',
      'chown ubuntu:ubuntu .env',
      'chmod 600 .env',  // Secure permissions for credentials file
      

      
      // Setup systemd service
      'cat > /etc/systemd/system/mcp-services.service << EOL',
      '[Unit]',
      'Description=MCP Services',
      'After=network.target',
      '',
      '[Service]',
      'Type=forking',
      'User=ubuntu',
      'Environment="HOME=/home/ubuntu"',
      'Environment="PATH=/home/ubuntu/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"',
      'WorkingDirectory=/home/ubuntu/demo_mcp_on_amazon_bedrock',
      'ExecStart=/bin/bash start_all.sh',
      'ExecStop=/bin/bash stop_all.sh',
      'Restart=always',
      '',
      '[Install]',
      'WantedBy=multi-user.target',
      'EOL',
      
      // Enable and start service
      'systemctl daemon-reload',
      'systemctl enable mcp-services',
      'systemctl start mcp-services'
    );

    // Create Launch Template
    const launchTemplate = new ec2.LaunchTemplate(this, `${prefix}-LaunchTemplate`, {
      instanceType: ec2.InstanceType.of(ec2.InstanceClass.C5, ec2.InstanceSize.XLARGE),
      machineImage: ec2.MachineImage.fromSsmParameter(
        '/aws/service/canonical/ubuntu/server/22.04/stable/current/amd64/hvm/ebs-gp2/ami-id',
        { os: ec2.OperatingSystemType.LINUX }
      ),
      userData,
      role,
      securityGroup: sg,
      blockDevices: [
        {
          deviceName: '/dev/sda1',
          volume: {
            ebsDevice: {
              volumeSize: 100,
              volumeType: ec2.EbsDeviceVolumeType.GP2,
            }
          }
        }
      ],
    });
    
    // Create Auto Scaling Group with Launch Template
    const asg = new autoscaling.AutoScalingGroup(this, `${prefix}-ASG`, {
      vpc,
      launchTemplate,
      minCapacity: 1,
      maxCapacity: 1,
      vpcSubnets: {
        subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS
      }
    });

    // Add ASG as target for ALB listeners
    streamlitListener.addTargets('Streamlit-Target', {
      port: 8502,
      protocol: elbv2.ApplicationProtocol.HTTP,
      targets: [asg],
      healthCheck: {
        path: '/',
        unhealthyThresholdCount: 2,
        healthyThresholdCount: 5,
        interval: cdk.Duration.seconds(30)
      }
    });

    // Stack Outputs
    new cdk.CfnOutput(this, 'Streamlit-Endpoint', {
      value: `http://${alb.loadBalancerDnsName}:8502`,
      description: 'Streamlit UI Endpoint'
    });

    // Output the API credentials
    new cdk.CfnOutput(this, 'ApiAccessKeyId', {
      value: accessKey.ref,
      description: 'API Access Key ID'
    });

    new cdk.CfnOutput(this, 'ApiSecretAccessKey', {
      value: accessKey.attrSecretAccessKey,
      description: 'API Secret Access Key'
    });
  }
}
