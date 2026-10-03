#include <iostream>
 
int main()
{
    float a {26};
    int b {5};
    float c {a / b};        // c = 5.2
    double d {4.0 / b};     // d = 0.8
    std::cout << "c = " << c << std::endl;
    std::cout << "d = " << d << std::endl;
}