function R = euler_to_rotation_matrix(RotX, RotY, RotZ)

    % Convert angles to radians
    RotX = deg2rad(RotX);
    RotY = deg2rad(RotY);
    RotZ = deg2rad(RotZ);

    % Define individual rotation matrices
    Rx = [1         , 0         , 0;
          0         , cos(RotX) , -sin(RotX);
          0         , sin(RotX) , cos(RotX)];
    
    Ry = [cos(RotY) , 0         , sin(RotY);
          0         , 1         , 0;
          -sin(RotY), 0         , cos(RotY)];
    
    Rz = [cos(RotZ) , -sin(RotZ), 0;
          sin(RotZ) , cos(RotZ) , 0;
          0         , 0         , 1];

    % Combine the rotations
    R = Rz * (Ry * Rx);

end
